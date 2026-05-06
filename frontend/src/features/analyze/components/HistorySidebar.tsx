import { formatDistanceToNow } from 'date-fns';
import { Trash2 } from 'lucide-react';
import { NavLink } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useAnalysisHistory } from '@/stores/analysisHistory';
import { cn } from '@/lib/utils';
import type { JobStatus } from '@/lib/types';

const statusVariant: Record<
  JobStatus,
  'default' | 'success' | 'warning' | 'destructive' | 'accent'
> = {
  pending: 'warning',
  running: 'accent',
  succeeded: 'success',
  failed: 'destructive',
};

export function HistorySidebar() {
  const entries = useAnalysisHistory((s) => s.entries);
  const clear = useAnalysisHistory((s) => s.clear);

  return (
    <aside className="hidden lg:col-span-3 lg:block">
      <div className="sticky top-24 border-l border-border pl-6">
        <div className="mb-4 flex items-center justify-between">
          <div className="marginalia">Recent runs</div>
          {entries.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-[10px]"
              onClick={clear}
            >
              <Trash2 className="h-3 w-3" />
              Clear
            </Button>
          )}
        </div>
        {entries.length === 0 ? (
          <p className="reading text-sm italic text-muted-foreground">
            No runs yet. Submit an analysis to see it appear here. History
            persists locally.
          </p>
        ) : (
          <ol className="space-y-4">
            {entries.map((e, i) => (
              <li key={e.jobId}>
                <NavLink
                  to={`/results/${e.jobId}`}
                  className={({ isActive }) =>
                    cn(
                      'group block border-l-2 border-transparent pl-3 transition-colors',
                      'hover:border-accent',
                      isActive && 'border-accent',
                    )
                  }
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="num text-[10px] text-muted-foreground/70">
                      {String(entries.length - i).padStart(2, '0')}
                    </span>
                    <Badge variant={statusVariant[e.status]}>{e.status}</Badge>
                  </div>
                  <div className="display mt-1 truncate text-sm text-foreground">
                    {e.label}
                  </div>
                  <div className="num mt-1 truncate text-[11px] text-muted-foreground">
                    {e.sourceIds.join(' · ')}
                  </div>
                  <div className="marginalia mt-1 text-[9px] text-muted-foreground/70">
                    {formatDistanceToNow(e.startedAt, { addSuffix: true })}
                  </div>
                </NavLink>
              </li>
            ))}
          </ol>
        )}
      </div>
    </aside>
  );
}
