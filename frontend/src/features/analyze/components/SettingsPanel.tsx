import { ChevronDown, RotateCcw } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { cn } from '@/lib/utils';
import type { AnalyzeSettings } from '@/lib/types';

// eslint-disable-next-line react-refresh/only-export-components
export const DEFAULT_SETTINGS: AnalyzeSettings = {
  window_sizes: [64, 128, 256],
  step_size: 16,
  bins: 8,
  top_p: 0.05,
  shift_d: 3,
  null_shifts_count: 50,
  alpha: 0.05,
  holdout_ratio: 0.0,
  min_pair_valid_fraction: 0.9,
  seed: 42,
};

export interface SettingsPanelProps {
  settings: AnalyzeSettings;
  onChange: (next: AnalyzeSettings) => void;
}

interface SliderRowProps {
  id: string;
  label: string;
  hint: string;
  min: number;
  max: number;
  step: number;
  value: number;
  format?: (v: number) => string;
  onChange: (v: number) => void;
}

function SliderRow({ id, label, hint, min, max, step, value, format, onChange }: SliderRowProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <Label htmlFor={id} className="num text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          {label}
        </Label>
        <span className="num text-sm text-foreground">
          {format ? format(value) : value}
        </span>
      </div>
      <Slider
        id={id}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.currentTarget.value))}
      />
      <p className="text-[12px] leading-snug text-muted-foreground">{hint}</p>
    </div>
  );
}

export function SettingsPanel({ settings, onChange }: SettingsPanelProps) {
  const [open, setOpen] = useState(false);

  const update = <K extends keyof AnalyzeSettings>(key: K, val: AnalyzeSettings[K]) => {
    onChange({ ...settings, [key]: val });
  };

  return (
    <div className="border-y border-border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 py-4 text-left transition-colors hover:bg-foreground/[0.02]"
      >
        <div>
          <div className="marginalia">Pipeline knobs</div>
          <div className="display mt-1 text-base">
            {open ? 'Hide settings' : 'Show settings'}
          </div>
        </div>
        <ChevronDown className={cn('h-4 w-4 transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="border-t border-border py-6">
          <div className="grid gap-7 md:grid-cols-2">
            <SliderRow
              id="top_p"
              label="top_p"
              hint="Top-p quantile of edges kept per window before scoring."
              min={0.001}
              max={0.5}
              step={0.001}
              value={settings.top_p}
              format={(v) => v.toFixed(3)}
              onChange={(v) => update('top_p', v)}
            />
            <SliderRow
              id="alpha"
              label="alpha — FDR target"
              hint="Benjamini–Hochberg false-discovery rate target."
              min={0.001}
              max={0.5}
              step={0.001}
              value={settings.alpha}
              format={(v) => v.toFixed(3)}
              onChange={(v) => update('alpha', v)}
            />
            <SliderRow
              id="holdout_ratio"
              label="holdout_ratio"
              hint="Fraction of trailing windows reserved for shift-control replication."
              min={0}
              max={0.49}
              step={0.01}
              value={settings.holdout_ratio}
              format={(v) => v.toFixed(2)}
              onChange={(v) => update('holdout_ratio', v)}
            />
            <SliderRow
              id="shift_d"
              label="shift_d"
              hint="Block size, in windows, for the circular-shift null distribution."
              min={0}
              max={20}
              step={1}
              value={settings.shift_d}
              onChange={(v) => update('shift_d', v)}
            />
            <div className="space-y-2">
              <Label htmlFor="null_shifts_count" className="num text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                null_shifts_count
              </Label>
              <Input
                id="null_shifts_count"
                type="number"
                min={10}
                max={2000}
                step={10}
                value={settings.null_shifts_count}
                onChange={(e) => update('null_shifts_count', Number(e.currentTarget.value))}
              />
              <p className="text-[12px] leading-snug text-muted-foreground">
                Number of random shifts used to build the null distribution.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="bins" className="num text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                bins
              </Label>
              <Input
                id="bins"
                type="number"
                min={2}
                max={64}
                step={1}
                value={settings.bins}
                onChange={(e) => update('bins', Number(e.currentTarget.value))}
              />
              <p className="text-[12px] leading-snug text-muted-foreground">
                Symbol-alphabet size used when tokenizing each window.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="step_size" className="num text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                step_size
              </Label>
              <Input
                id="step_size"
                type="number"
                min={1}
                max={256}
                step={1}
                value={settings.step_size}
                onChange={(e) => update('step_size', Number(e.currentTarget.value))}
              />
              <p className="text-[12px] leading-snug text-muted-foreground">
                Step (in samples) between consecutive sliding windows.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="seed" className="num text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                seed
              </Label>
              <Input
                id="seed"
                type="number"
                step={1}
                value={settings.seed}
                onChange={(e) => update('seed', Number(e.currentTarget.value))}
              />
              <p className="text-[12px] leading-snug text-muted-foreground">
                RNG seed for circular-shift sampling. Fixed for reproducible runs.
              </p>
            </div>
          </div>

          <div className="mt-7 flex justify-end">
            <Button type="button" size="sm" variant="ghost" onClick={() => onChange(DEFAULT_SETTINGS)}>
              <RotateCcw className="h-3.5 w-3.5" />
              Reset to defaults
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
