import { Globe, Lock, WifiOff } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import type { SourceMeta } from '@/lib/types';

export interface SourceSelectProps {
  sources: SourceMeta[] | undefined;
  isLoading: boolean;
  isError: boolean;
  selected: string[];
  onChange: (next: string[]) => void;
}

export function SourceSelect({
  sources,
  isLoading,
  isError,
  selected,
  onChange,
}: SourceSelectProps) {
  if (isLoading) {
    return (
      <ul className="divide-y divide-border border-y border-border">
        {Array.from({ length: 4 }).map((_, i) => (
          <li key={i} className="py-4">
            <Skeleton className="h-12 w-full" />
          </li>
        ))}
      </ul>
    );
  }

  if (isError || !sources) {
    return (
      <div className="border-l-2 border-destructive py-4 pl-4 text-sm text-destructive">
        Failed to load source catalogue. Is the backend running on{' '}
        <code className="num">/api</code>?
      </div>
    );
  }

  const toggle = (id: string) => {
    if (selected.includes(id)) onChange(selected.filter((s) => s !== id));
    else onChange([...selected, id]);
  };

  return (
    <ul className="divide-y divide-border border-y border-border">
      {sources.map((src) => {
        const disabled = src.status === 'coming_soon';
        const checked = selected.includes(src.id);
        return (
          <li key={src.id}>
            <button
              type="button"
              disabled={disabled}
              role="checkbox"
              aria-checked={checked}
              onClick={() => !disabled && toggle(src.id)}
              className={cn(
                'group grid w-full grid-cols-12 items-baseline gap-4 py-5 text-left transition-colors',
                'hover:bg-foreground/[0.02]',
                checked && 'bg-accent/[0.05]',
                disabled && 'cursor-not-allowed opacity-50',
              )}
            >
              {/* Selection indicator */}
              <div className="col-span-1 flex items-center justify-center">
                <span
                  aria-hidden
                  className={cn(
                    'h-3 w-3 border transition-colors',
                    checked
                      ? 'border-accent bg-accent'
                      : 'border-border group-hover:border-foreground',
                  )}
                />
              </div>

              {/* Identifier + label */}
              <div className="col-span-11 md:col-span-4">
                <div className="num text-xs uppercase tracking-[0.16em] text-muted-foreground">
                  {src.id}
                </div>
                <div className="display mt-1 text-lg leading-tight">{src.label}</div>
              </div>

              {/* Description */}
              <p className="col-span-12 text-sm text-muted-foreground md:col-span-5">
                {src.description}
              </p>

              {/* Status + cadence */}
              <div className="col-span-12 flex items-center justify-end gap-2 md:col-span-2">
                {disabled ? (
                  <Badge variant="warning">
                    <Lock className="h-3 w-3" /> Pending
                  </Badge>
                ) : src.requires_internet ? (
                  <Badge variant="default">
                    <Globe className="h-3 w-3" /> Live
                  </Badge>
                ) : (
                  <Badge variant="success">
                    <WifiOff className="h-3 w-3" /> Offline
                  </Badge>
                )}
              </div>
              <div className="col-span-12 mt-1 flex items-baseline justify-between text-[10px] md:col-span-12">
                <span className="marginalia">{src.domain}</span>
                <span className="num text-muted-foreground/70">{src.cadence}</span>
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
