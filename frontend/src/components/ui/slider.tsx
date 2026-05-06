import { forwardRef, type InputHTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

export type SliderProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>;

/*
 * Editorial slider — a thin warm rule with a single ink square as the thumb.
 * The track is hairline, not chunky.
 */
export const Slider = forwardRef<HTMLInputElement, SliderProps>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      type="range"
      className={cn(
        'h-px w-full cursor-pointer appearance-none bg-border outline-none',
        '[&::-webkit-slider-runnable-track]:h-px [&::-webkit-slider-runnable-track]:bg-border',
        '[&::-webkit-slider-thumb]:appearance-none',
        '[&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4',
        '[&::-webkit-slider-thumb]:-translate-y-[7px]',
        '[&::-webkit-slider-thumb]:rounded-none [&::-webkit-slider-thumb]:bg-foreground',
        '[&::-webkit-slider-thumb]:transition-colors',
        'hover:[&::-webkit-slider-thumb]:bg-accent',
        '[&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4',
        '[&::-moz-range-thumb]:rounded-none [&::-moz-range-thumb]:border-0',
        '[&::-moz-range-thumb]:bg-foreground',
        'hover:[&::-moz-range-thumb]:bg-accent',
        'focus-visible:outline-none',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  ),
);
Slider.displayName = 'Slider';
