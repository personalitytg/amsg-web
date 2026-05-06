import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { PValueBucket } from '@/lib/types';

export interface PValueHistogramProps {
  buckets: PValueBucket[];
  alpha: number;
}

// Editorial-dark palette.
const ink = 'rgb(232, 221, 201)';
const subInk = 'rgb(139, 130, 117)';
const sienna = 'rgb(212, 103, 62)';
const grid = 'rgba(232, 221, 201, 0.06)';

export function PValueHistogram({ buckets, alpha }: PValueHistogramProps) {
  const data = buckets.map((b) => ({
    x: (b.bin_start + b.bin_end) / 2,
    range: `${b.bin_start.toFixed(2)} – ${b.bin_end.toFixed(2)}`,
    count: b.count,
  }));

  if (data.every((d) => d.count === 0)) {
    return (
      <div className="flex h-40 items-center justify-center text-sm italic text-muted-foreground">
        No edges scored — the histogram is empty.
      </div>
    );
  }

  return (
    <div className="h-[280px] w-full">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="2 4" stroke={grid} vertical={false} />
          <XAxis
            dataKey="x"
            type="number"
            domain={[0, 1]}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            tick={{ fill: subInk, fontSize: 10, fontFamily: 'IBM Plex Mono' }}
            axisLine={{ stroke: subInk, strokeWidth: 0.5 }}
            tickLine={{ stroke: subInk }}
          />
          <YAxis
            tick={{ fill: subInk, fontSize: 10, fontFamily: 'IBM Plex Mono' }}
            axisLine={{ stroke: subInk, strokeWidth: 0.5 }}
            tickLine={{ stroke: subInk }}
            allowDecimals={false}
            width={40}
          />
          <Tooltip
            contentStyle={{
              background: 'rgb(27, 24, 20)',
              border: '1px solid rgba(232, 221, 201, 0.2)',
              borderRadius: 0,
              fontSize: 11,
              fontFamily: 'IBM Plex Mono',
              color: ink,
            }}
            cursor={{ fill: 'rgba(212, 103, 62, 0.05)' }}
            labelFormatter={(_, p) => p[0]?.payload?.range ?? ''}
            formatter={(v: number) => [v, 'edges']}
          />
          <ReferenceLine
            x={alpha}
            stroke={sienna}
            strokeDasharray="4 4"
            label={{
              value: `α = ${alpha}`,
              fill: sienna,
              fontSize: 10,
              fontFamily: 'IBM Plex Mono',
              position: 'top',
            }}
          />
          <Bar dataKey="count" fill={ink} radius={[0, 0, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
