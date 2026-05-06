import { cn } from '@/lib/utils';
import type { JobProgress, JobStatus } from '@/lib/types';

export interface ProgressCardProps {
  jobId: string;
  status: JobStatus;
  progress: JobProgress;
  error?: string | null;
}

const stageOrder = ['queued', 'fetch', 'pipeline', 'aggregate', 'done'];

export function ProgressCard({ jobId, status, progress, error }: ProgressCardProps) {
  const pct = Math.max(0, Math.min(100, progress.percent));
  const isFailed = status === 'failed';
  const isDone = status === 'succeeded';

  return (
    <div
      className={cn(
        'border-y border-border py-6',
        isDone && 'border-sage',
        isFailed && 'border-destructive',
      )}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2 pb-4">
        <div>
          <div className="marginalia text-accent">
            {isDone ? 'Run complete' : isFailed ? 'Run failed' : 'Run in progress'}
          </div>
          <div className="display mt-1 text-xl">
            {progress.message || progress.stage || 'Working…'}
          </div>
        </div>
        <div className="text-right">
          <div className="marginalia text-muted-foreground">Job</div>
          <div className="num mt-1 text-sm text-muted-foreground">{jobId.slice(0, 12)}…</div>
        </div>
      </div>

      {/* Tape progress — a thick rule that fills with sienna. */}
      <div className="relative h-px bg-border">
        <div
          className={cn(
            'absolute left-0 top-0 h-px transition-[width] duration-500',
            isFailed ? 'bg-destructive' : 'bg-accent',
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-2 flex items-baseline justify-between text-[10px]">
        <span className="marginalia">{progress.stage}</span>
        <span className="num text-muted-foreground">{pct.toFixed(0)}%</span>
      </div>

      {/* Stage roman dots — like a contents leader in a book. */}
      <ol className="mt-6 grid grid-cols-5 gap-2">
        {stageOrder.map((stage, i) => {
          const idx = stageOrder.indexOf(progress.stage);
          const reached = idx >= i || isDone;
          return (
            <li
              key={stage}
              className={cn(
                'flex flex-col items-center gap-1 border-t pt-2 transition-colors',
                reached ? 'border-accent text-accent' : 'border-border text-muted-foreground/60',
              )}
            >
              <span className="num text-[10px]">{String(i + 1).padStart(2, '0')}</span>
              <span className="marginalia text-[9px]">{stage}</span>
            </li>
          );
        })}
      </ol>

      {error && (
        <p className="mt-6 border-l-2 border-destructive py-2 pl-4 text-sm italic text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
