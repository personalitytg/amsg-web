import { cva, type VariantProps } from 'class-variance-authority';
import type { HTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

/*
 * Editorial chip. Sharp-cornered, single hairline. Color is communicated
 * by ink, not fill — a tiny printed label rather than a bubble.
 */
const badgeVariants = cva(
  cn(
    'inline-flex items-center gap-1 rounded-none border px-2 py-0.5',
    'font-mono text-[10px] uppercase tracking-[0.16em]',
  ),
  {
    variants: {
      variant: {
        default: 'border-border bg-transparent text-foreground',
        secondary: 'border-border bg-secondary text-secondary-foreground',
        destructive:
          'border-destructive/60 bg-transparent text-destructive',
        success: 'border-sage/60 bg-transparent text-sage',
        warning: 'border-mark/60 bg-transparent text-mark',
        outline: 'border-border bg-transparent text-muted-foreground',
        accent: 'border-accent/70 bg-transparent text-accent',
      },
    },
    defaultVariants: { variant: 'default' },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
