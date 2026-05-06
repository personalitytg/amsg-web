import { cn } from '@/lib/utils';
import type { JobProgress, JobStatus } from '@/lib/types';

export interface ProgressCardLiteProps {
  jobId: string;
  status: JobStatus;
  progress: JobProgress;
}

export function ProgressCardLite({ jobId, status, progress }: ProgressCardLiteProps) {
  const pct = Math.max(0, Math.min(100, progress.percent));
  return (
    <div className="border-y border-border py-8">
      <div className="flex items-baseline justify-between">
        <div>
          <div className="marginalia text-accent">
            {status === 'pending' ? 'Queued' : 'Running'}
          </div>
          <div className="display mt-1 text-2xl">
            {progress.message || progress.stage || 'Working…'}
          </div>
        </div>
        <div className="text-right">
          <div className="num text-xs text-muted-foreground">{jobId.slice(0, 12)}…</div>
          <div className="num mt-1 text-2xl text-accent">{pct.toFixed(0)}%</div>
        </div>
      </div>
      <div className="relative mt-6 h-px bg-border">
        <div
          className={cn(
            'absolute left-0 top-0 h-px bg-accent transition-[width] duration-500',
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="reading mt-6 text-sm italic text-muted-foreground">
        The dashboard will load automatically when the job finishes — no need
        to refresh.
      </p>
    </div>
  );
}
