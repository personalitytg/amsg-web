import type { HTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

/*
 * Editorial skeleton. No shimmer — instead, a slow ink-tick pulse.
 * Reads as printed-on-paper rather than chrome.
 */
export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'rounded-none border border-border/60 bg-secondary/60',
        'animate-tick',
        className,
      )}
      {...props}
    />
  );
}
