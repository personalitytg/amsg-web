import type { Layout } from 'plotly.js';
import { useMemo } from 'react';
// @ts-expect-error — plotly.js-dist-min ships no .d.ts; the factory accepts any module.
import Plotly from 'plotly.js-dist-min';
import createPlotlyComponent from 'react-plotly.js/factory';

import type { AnomalyEvent, SeriesPayload } from '@/lib/types';

const Plot = createPlotlyComponent(Plotly);

// Editorial dark palette (matches index.css).
const ink = 'rgb(232, 221, 201)'; // bone-ish for line strokes on dark
const subInk = 'rgb(139, 130, 117)'; // warm taupe
const grid = 'rgba(232, 221, 201, 0.06)';
const sienna = 'rgb(212, 103, 62)';
const siennaSoft = 'rgba(212, 103, 62, 0.18)';

export interface SeriesChartProps {
  series: SeriesPayload[];
  events: AnomalyEvent[];
  highlightedEventId?: string | null;
  alpha: number;
}

export function SeriesChart({ series, events, highlightedEventId, alpha }: SeriesChartProps) {
  const traces = useMemo(
    () =>
      series.map((s, i) => ({
        type: 'scattergl' as const,
        mode: 'lines' as const,
        x: s.points.map((p) => p.t),
        y: s.points.map((p) => p.v),
        name: s.label,
        xaxis: 'x',
        yaxis: `y${i === 0 ? '' : i + 1}`,
        line: { width: 1.1, color: ink },
        hovertemplate: `%{x}<br>${s.label}: %{y:.4g}<extra></extra>`,
      })),
    [series],
  );

  const layout = useMemo<Partial<Layout>>(() => {
    const rows = Math.max(series.length, 1);
    const gap = 0.04;
    const rowH = (1 - gap * (rows - 1)) / rows;
    const yAxes: Record<string, unknown> = {};
    series.forEach((s, i) => {
      const top = 1 - i * (rowH + gap);
      const bottom = top - rowH;
      const key = `yaxis${i === 0 ? '' : i + 1}`;
      yAxes[key] = {
        domain: [Math.max(0, bottom), Math.min(1, top)],
        title: { text: s.label, font: { size: 10, family: 'IBM Plex Mono', color: subInk } },
        gridcolor: grid,
        zeroline: false,
        automargin: true,
        tickfont: { family: 'IBM Plex Mono', size: 9, color: subInk },
        linecolor: 'rgba(232, 221, 201, 0.18)',
      };
    });

    const shapes = events.map((e) => {
      const isSig = (e.q_value ?? e.best_p_value) <= alpha;
      const isHighlight = e.event_id === highlightedEventId;
      const fill = isHighlight
        ? 'rgba(212, 103, 62, 0.32)'
        : isSig
          ? siennaSoft
          : 'rgba(232, 221, 201, 0.05)';
      const line = isHighlight
        ? sienna
        : isSig
          ? 'rgba(212, 103, 62, 0.55)'
          : 'rgba(232, 221, 201, 0.18)';
      return {
        type: 'rect' as const,
        xref: 'x' as const,
        yref: 'paper' as const,
        x0: e.start,
        x1: e.end,
        y0: 0,
        y1: 1,
        fillcolor: fill,
        line: { color: line, width: isHighlight ? 1.5 : 0.5 },
      };
    });

    return {
      autosize: true,
      height: Math.max(220, 140 * rows + 60),
      margin: { l: 64, r: 16, t: 14, b: 36 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { family: 'Albert Sans, system-ui', size: 11, color: ink },
      showlegend: false,
      xaxis: {
        type: 'date' as const,
        gridcolor: grid,
        zeroline: false,
        rangeslider: { visible: false },
        tickfont: { family: 'IBM Plex Mono', size: 9, color: subInk },
        linecolor: 'rgba(232, 221, 201, 0.18)',
      },
      ...yAxes,
      shapes,
      hovermode: 'x unified' as const,
      hoverlabel: {
        bgcolor: 'rgb(27, 24, 20)',
        bordercolor: 'rgba(232, 221, 201, 0.2)',
        font: { family: 'IBM Plex Mono', size: 11, color: ink },
      },
    };
  }, [series, events, highlightedEventId, alpha]);

  if (series.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm italic text-muted-foreground">
        No series returned.
      </div>
    );
  }

  return (
    <Plot
      data={traces}
      layout={layout}
      style={{ width: '100%' }}
      config={{
        responsive: true,
        displaylogo: false,
        modeBarButtonsToRemove: ['lasso2d', 'select2d'],
      }}
      useResizeHandler
    />
  );
}
