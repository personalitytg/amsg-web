import { formatDuration, formatPValue } from '@/lib/utils';
import type { AnalysisSummary } from '@/lib/types';

export interface HeroMetricsProps {
  summary: AnalysisSummary;
  alpha: number;
}

interface MetricProps {
  label: string;
  value: string;
  hint: string;
  emphasize?: boolean;
}

function Metric({ label, value, hint, emphasize }: MetricProps) {
  return (
    <div className="border-l border-border pl-5 first:border-l-0 first:pl-0">
      <div className="marginalia">{label}</div>
      <div
        className={
          'num mt-2 text-3xl tracking-tight md:text-5xl ' +
          (emphasize ? 'text-accent' : 'text-foreground')
        }
      >
        {value}
      </div>
      <div className="reading mt-2 text-xs text-muted-foreground">{hint}</div>
    </div>
  );
}

export function HeroMetrics({ summary, alpha }: HeroMetricsProps) {
  return (
    <div className="grid grid-cols-2 gap-x-6 gap-y-8 border-y border-border py-10 md:grid-cols-4">
      <Metric
        label="Events"
        value={String(summary.total_events)}
        hint={`across ${summary.sources_count} sources`}
      />
      <Metric
        label={`Significant · q ≤ ${alpha}`}
        value={String(summary.significant_events)}
        hint={summary.significant_events === 0 ? 'null result — see disclaimer' : 'after BH-FDR'}
        emphasize={summary.significant_events > 0}
      />
      <Metric
        label="Min p-value"
        value={formatPValue(summary.p_value_min)}
        hint={summary.p_value_min === null ? 'no events' : 'best edge p-value'}
      />
      <Metric
        label="Duration"
        value={formatDuration(summary.duration_seconds)}
        hint="end-to-end pipeline"
      />
    </div>
  );
}
