import { format, isBefore, subDays } from 'date-fns';
import { CalendarDays } from 'lucide-react';
import { useState } from 'react';
import { DayPicker, type DateRange } from 'react-day-picker';
import 'react-day-picker/dist/style.css';

import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';

export interface DateRangePickerProps {
  value: DateRange | undefined;
  onChange: (range: DateRange | undefined) => void;
  className?: string;
}

const presets: { label: string; days: number }[] = [
  { label: 'Last 7 days', days: 7 },
  { label: 'Last 30 days', days: 30 },
  { label: 'Last 90 days', days: 90 },
];

export function DateRangePicker({ value, onChange, className }: DateRangePickerProps) {
  const [open, setOpen] = useState(false);

  const display = (() => {
    if (!value?.from) return 'Pick a date range';
    if (!value.to) return format(value.from, 'PP');
    return `${format(value.from, 'PP')} → ${format(value.to, 'PP')}`;
  })();

  const applyPreset = (days: number) => {
    const today = new Date();
    onChange({ from: subDays(today, days - 1), to: today });
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className={cn(
            'h-10 w-full justify-start gap-2 font-normal',
            !value?.from && 'text-muted-foreground',
            className,
          )}
        >
          <CalendarDays className="h-4 w-4" />
          {display}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <div className="flex flex-col gap-2 border-b p-2 sm:flex-row sm:items-center">
          {presets.map((p) => (
            <Button
              key={p.label}
              size="sm"
              variant="ghost"
              className="h-8 justify-start text-xs"
              onClick={() => applyPreset(p.days)}
            >
              {p.label}
            </Button>
          ))}
        </div>
        <DayPicker
          mode="range"
          numberOfMonths={2}
          selected={value}
          onSelect={onChange}
          disabled={(d) => isBefore(new Date(), d)}
          className="rdp-amsg p-3"
          classNames={{
            caption_label: 'text-sm font-medium',
            head_cell: 'text-muted-foreground text-[0.7rem] font-medium',
            day: 'h-9 w-9 rounded-md text-sm hover:bg-accent/15',
            day_selected:
              'bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground',
            day_range_middle: 'bg-primary/15 text-foreground',
            day_today: 'underline underline-offset-2',
            day_disabled: 'opacity-30 cursor-not-allowed',
            nav_button:
              'h-7 w-7 inline-flex items-center justify-center rounded-md hover:bg-accent/15',
          }}
        />
      </PopoverContent>
    </Popover>
  );
}
