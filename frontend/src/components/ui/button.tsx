import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { forwardRef, type ButtonHTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

/*
 * Editorial buttons. Three real variants:
 *   ink      — primary action. Solid parchment-on-bistre fill.
 *   sienna   — accent action (Run, Submit). Burnt-sienna fill.
 *   outline  — quiet outlined button.
 *   ghost    — text-only.
 *   link     — inline editorial link.
 *
 * `default` and `gradient` are kept as backward-compat aliases so existing
 * call sites don't crash; they map to `ink` and `sienna` respectively.
 */
const buttonVariants = cva(
  cn(
    'group relative inline-flex items-center justify-center gap-2 whitespace-nowrap',
    'rounded-sm text-sm font-medium tracking-tight',
    'transition-[background-color,color,border-color,transform] duration-200',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background',
    'disabled:pointer-events-none disabled:opacity-50',
    '[&_svg]:size-4 [&_svg]:shrink-0',
  ),
  {
    variants: {
      variant: {
        ink:
          'border border-foreground/90 bg-foreground text-background hover:bg-foreground/90 hover:-translate-y-px',
        default:
          'border border-foreground/90 bg-foreground text-background hover:bg-foreground/90 hover:-translate-y-px',
        sienna:
          'border border-accent bg-accent text-accent-foreground hover:bg-accent/90 hover:-translate-y-px',
        gradient:
          'border border-accent bg-accent text-accent-foreground hover:bg-accent/90 hover:-translate-y-px',
        destructive:
          'border border-destructive bg-destructive text-destructive-foreground hover:bg-destructive/90',
        outline:
          'border border-border bg-transparent text-foreground hover:border-accent hover:text-accent',
        secondary:
          'border border-border bg-secondary text-secondary-foreground hover:bg-secondary/80',
        ghost: 'border border-transparent text-foreground hover:bg-foreground/5',
        link:
          'h-auto rounded-none border-0 px-0 py-0 text-accent underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-10 px-5 py-2',
        sm: 'h-8 px-3 text-xs',
        lg: 'h-12 px-7 text-[15px]',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: {
      variant: 'ink',
      size: 'default',
    },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    );
  },
);
Button.displayName = 'Button';

// eslint-disable-next-line react-refresh/only-export-components
export { buttonVariants };
