import type { AnalysisResult, AnomalyEvent } from '@/lib/types';

function csvCell(v: unknown): string {
  if (v === null || v === undefined) return '';
  const s = typeof v === 'object' ? JSON.stringify(v) : String(v);
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

export function eventsToCsv(events: AnomalyEvent[]): string {
  const header = [
    'event_id',
    'start',
    'end',
    'best_p_value',
    'q_value',
    'best_nms',
    'edge_novelty_sum',
    'edges_count',
    'cross_domain_edges_count',
    'is_holdout',
    'sources',
    'domains',
  ];
  const rows = events.map((e) =>
    [
      e.event_id,
      e.start,
      e.end,
      e.best_p_value,
      e.q_value ?? '',
      e.best_nms,
      e.edge_novelty_sum,
      e.edges_count,
      e.cross_domain_edges_count,
      e.is_holdout,
      e.sources.join('|'),
      e.domains.join('|'),
    ]
      .map(csvCell)
      .join(','),
  );
  return [header.join(','), ...rows].join('\n');
}

function downloadBlob(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function downloadEventsCsv(events: AnomalyEvent[], jobId: string): void {
  downloadBlob(
    `amsg-${jobId.slice(0, 8)}-events.csv`,
    new Blob([eventsToCsv(events)], { type: 'text/csv;charset=utf-8' }),
  );
}

export function downloadResultJson(result: AnalysisResult): void {
  downloadBlob(
    `amsg-${result.job_id.slice(0, 8)}-result.json`,
    new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }),
  );
}
