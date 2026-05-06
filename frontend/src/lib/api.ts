import axios, { type AxiosError } from 'axios';

import type {
  AnalyzeAccepted,
  AnalyzeRequest,
  JobEnvelope,
  JobProgress,
  SourceListResponse,
} from './types';

const baseURL = import.meta.env.VITE_API_BASE_URL ?? '/api';

export const http = axios.create({
  baseURL,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
});

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
    this.name = 'ApiError';
  }
}

function unwrap<T>(promise: Promise<{ data: T }>): Promise<T> {
  return promise
    .then((r) => r.data)
    .catch((err: AxiosError<{ detail?: string }>) => {
      const status = err.response?.status ?? 0;
      const detail =
        err.response?.data?.detail ?? err.message ?? 'Network or server error';
      throw new ApiError(status, detail);
    });
}

export const api = {
  health: (): Promise<{ status: string }> => unwrap(http.get('/health')),

  listSources: (): Promise<SourceListResponse> => unwrap(http.get('/sources')),

  startAnalysis: (req: AnalyzeRequest): Promise<AnalyzeAccepted> =>
    unwrap(http.post('/analyze', req)),

  getAnalysis: (jobId: string): Promise<JobEnvelope> =>
    unwrap(http.get(`/analysis/${jobId}`)),
};

/**
 * Subscribe to SSE progress events for a job.
 * Returns an unsubscribe function.
 */
export function subscribeProgress(
  jobId: string,
  onMessage: (msg: JobProgress & { status: string }) => void,
  onDone: (info: { status: string; error: string | null }) => void,
  onError?: (err: Event) => void,
): () => void {
  const url = `${baseURL}/analysis/${jobId}/progress`;
  const source = new EventSource(url);

  source.addEventListener('progress', (evt) => {
    try {
      const data = JSON.parse((evt as MessageEvent).data);
      onMessage(data);
    } catch {
      /* ignore malformed payloads */
    }
  });

  source.addEventListener('done', (evt) => {
    try {
      const data = JSON.parse((evt as MessageEvent).data);
      onDone(data);
    } catch {
      onDone({ status: 'unknown', error: null });
    }
    source.close();
  });

  source.onerror = (evt) => {
    onError?.(evt);
    source.close();
  };

  return () => source.close();
}
