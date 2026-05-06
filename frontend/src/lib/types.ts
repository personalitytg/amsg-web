/**
 * Wire types mirroring `backend/app/schemas/*.py`.
 * Keep the field names identical — the API speaks snake_case.
 */

export type SourceStatus = 'available' | 'coming_soon';

export interface SourceParam {
  name: string;
  label: string;
  description: string;
  default: string | number | boolean | null;
}

export interface SourceMeta {
  id: string;
  label: string;
  domain: string;
  description: string;
  cadence: string;
  requires_internet: boolean;
  status: SourceStatus;
  extra_params: SourceParam[];
}

export interface SourceListResponse {
  sources: SourceMeta[];
}

export interface AnalyzeSettings {
  window_sizes: number[];
  step_size: number;
  bins: number;
  top_p: number;
  shift_d: number;
  null_shifts_count: number;
  alpha: number;
  holdout_ratio: number;
  min_pair_valid_fraction: number;
  seed: number;
}

export interface AnalyzeRequest {
  source_ids: string[];
  start: string; // ISO date YYYY-MM-DD
  end: string;
  settings?: Partial<AnalyzeSettings>;
  label?: string;
}

export interface AnalyzeAccepted {
  job_id: string;
  status: 'pending' | 'running';
}

export type JobStatus = 'pending' | 'running' | 'succeeded' | 'failed';

export interface JobProgress {
  stage: string;
  percent: number;
  message: string;
}

export interface JobEnvelope {
  id: string;
  status: JobStatus;
  progress: JobProgress;
  error: string | null;
  created_at: number;
  finished_at: number | null;
  result?: AnalysisResult;
}

export interface SeriesPoint {
  t: string;
  v: number | null;
}

export interface SeriesPayload {
  source_id: string;
  domain: string;
  label: string;
  points: SeriesPoint[];
}

export interface EventEdge {
  a: string;
  b: string;
  nms: number;
  p_value: number;
  novelty: number;
}

export interface AnomalyEvent {
  event_id: string;
  start: string;
  end: string;
  best_p_value: number;
  q_value: number | null;
  best_nms: number;
  edge_novelty_sum: number;
  edges_count: number;
  sources: string[];
  domains: string[];
  cross_domain_edges_count: number;
  top_edges: EventEdge[];
  is_holdout: boolean;
}

export interface HeatmapCell {
  a: string;
  b: string;
  score: number;
}

export interface PValueBucket {
  bin_start: number;
  bin_end: number;
  count: number;
}

export interface AnalysisSummary {
  total_events: number;
  significant_events: number;
  p_value_min: number | null;
  p_value_max: number | null;
  sources_count: number;
  duration_seconds: number;
}

export interface AnalysisResult {
  job_id: string;
  summary: AnalysisSummary;
  series: SeriesPayload[];
  events: AnomalyEvent[];
  heatmap: HeatmapCell[];
  p_value_histogram: PValueBucket[];
  config_echo: Record<string, unknown>;
}
