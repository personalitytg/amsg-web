import { useMemo } from 'react';
import {
  Area,
  AreaChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

interface Point {
  i: number;
  v: number;
}

function generateSyntheticSeries(): Point[] {
  // Deterministic pseudo-noise (mulberry32) so the chart is bit-stable.
  let s = 0x6d2b79f5;
  const rand = () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4_294_967_296;
  };

  const out: Point[] = [];
  for (let i = 0; i < 200; i++) {
    const base = Math.sin(i / 12) * 0.6 + Math.cos(i / 28) * 0.3;
    const noise = (rand() - 0.5) * 0.5;
    const burst =
      i >= 110 && i <= 138
        ? Math.sin((i - 110) / 4) * 1.4 + (rand() - 0.5) * 1.2
        : 0;
    out.push({ i, v: base + noise + burst });
  }
  return out;
}

// Editorial palette for plates (matches index.css --paper / --paper-ink).
const ink = 'hsl(30 22% 12%)';
const subInk = 'hsl(30 14% 38%)';
const sienna = 'hsl(14 60% 42%)';
const paper = 'hsl(38 30% 90%)';

export function SamplePreview() {
  const data = useMemo(generateSyntheticSeries, []);

  return (
    <div className="h-[260px] w-full">
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="sample-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={ink} stopOpacity={0.18} />
              <stop offset="100%" stopColor={ink} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="i"
            tick={{ fill: subInk, fontSize: 10, fontFamily: 'IBM Plex Mono' }}
            axisLine={{ stroke: subInk, strokeWidth: 0.5 }}
            tickLine={{ stroke: subInk }}
          />
          <YAxis
            tick={{ fill: subInk, fontSize: 10, fontFamily: 'IBM Plex Mono' }}
            axisLine={{ stroke: subInk, strokeWidth: 0.5 }}
            tickLine={{ stroke: subInk }}
            width={36}
          />
          <Tooltip
            contentStyle={{
              background: paper,
              border: `1px solid ${subInk}`,
              borderRadius: 0,
              fontSize: 11,
              fontFamily: 'IBM Plex Mono',
              color: ink,
            }}
            labelStyle={{ color: subInk }}
            cursor={{ stroke: sienna, strokeDasharray: '3 3', strokeWidth: 1 }}
            formatter={(v: number) => [v.toFixed(3), 'value']}
            labelFormatter={(l) => `t = ${l}`}
          />
          <ReferenceArea
            x1={110}
            x2={138}
            y1="auto"
            y2="auto"
            fill={sienna}
            fillOpacity={0.1}
            stroke={sienna}
            strokeOpacity={0.6}
            strokeDasharray="2 4"
            label={{
              value: 'candidate event',
              position: 'insideTopRight',
              fill: sienna,
              fontSize: 10,
              fontFamily: 'IBM Plex Mono',
            }}
          />
          <Area
            type="monotone"
            dataKey="v"
            stroke={ink}
            strokeWidth={1.4}
            fill="url(#sample-fill)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
