import { Fragment, useMemo, useState } from 'react';

import { cn } from '@/lib/utils';
import type { HeatmapCell } from '@/lib/types';

export interface HeatmapPanelProps {
  cells: HeatmapCell[];
}

interface Cell {
  a: string;
  b: string;
  score: number;
}

/*
 * Editorial heatmap. Monochrome warm dark gradient (background → sienna)
 * — never the AI-default purple/cyan. Cells are sharp squares with
 * hairline separators, like a printed truth-table.
 */
function colorFor(score: number, min: number, max: number): string {
  if (max <= min) return 'hsl(32 12% 14%)';
  const t = (score - min) / (max - min);
  // Interpolate from background-ish to sienna in HSL.
  const h = 32 + (14 - 32) * t; // hue from warm-near-bg to sienna
  const s = 12 + (60 - 12) * t;
  const l = 14 + (50 - 14) * t;
  return `hsl(${h.toFixed(0)} ${s.toFixed(0)}% ${l.toFixed(0)}%)`;
}

export function HeatmapPanel({ cells }: HeatmapPanelProps) {
  const { labels, matrix, scoreMin, scoreMax } = useMemo(() => {
    const set = new Set<string>();
    cells.forEach((c) => {
      set.add(c.a);
      set.add(c.b);
    });
    const lbls = Array.from(set).sort();
    const idx = new Map(lbls.map((l, i) => [l, i]));
    const m: (Cell | null)[][] = Array.from({ length: lbls.length }, () =>
      Array(lbls.length).fill(null),
    );
    let mn = Infinity;
    let mx = -Infinity;
    for (const c of cells) {
      const i = idx.get(c.a);
      const j = idx.get(c.b);
      if (i === undefined || j === undefined) continue;
      m[i][j] = c;
      m[j][i] = { a: c.b, b: c.a, score: c.score };
      mn = Math.min(mn, c.score);
      mx = Math.max(mx, c.score);
    }
    return { labels: lbls, matrix: m, scoreMin: mn, scoreMax: mx };
  }, [cells]);

  const [hovered, setHovered] = useState<Cell | null>(null);

  if (labels.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm italic text-muted-foreground">
        No pairs available.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto">
        <div className="inline-block min-w-full">
          <div
            className="grid gap-px bg-border"
            style={{
              gridTemplateColumns: `auto repeat(${labels.length}, minmax(36px, 1fr))`,
            }}
          >
            <div className="bg-background" />
            {labels.map((l) => (
              <div
                key={`col-${l}`}
                className="num bg-background px-1 pb-1 text-center text-[9px] uppercase tracking-[0.16em] text-muted-foreground"
                title={l}
              >
                {l}
              </div>
            ))}
            {labels.map((row, i) => (
              <Fragment key={`row-${row}`}>
                <div
                  className="num bg-background pr-2 text-right text-[9px] uppercase tracking-[0.16em] text-muted-foreground"
                  title={row}
                >
                  {row}
                </div>
                {labels.map((col, j) => {
                  const cell = matrix[i][j];
                  const isDiag = i === j;
                  return (
                    <div
                      key={`${row}-${col}`}
                      onMouseEnter={() => cell && setHovered(cell)}
                      onMouseLeave={() => setHovered(null)}
                      className={cn(
                        'aspect-square transition-transform',
                        cell && 'cursor-pointer hover:scale-[1.06] hover:outline hover:outline-1 hover:outline-accent',
                      )}
                      style={{
                        background: isDiag
                          ? 'hsl(32 12% 10%)'
                          : cell
                            ? colorFor(cell.score, scoreMin, scoreMax)
                            : 'hsl(32 12% 14% / 0.4)',
                      }}
                    />
                  );
                })}
              </Fragment>
            ))}
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="num text-[10px] text-muted-foreground">
            {scoreMin.toFixed(3)}
          </span>
          <div
            className="h-1.5 w-32"
            style={{
              background: `linear-gradient(to right, ${colorFor(scoreMin, scoreMin, scoreMax)}, ${colorFor(scoreMax, scoreMin, scoreMax)})`,
            }}
          />
          <span className="num text-[10px] text-muted-foreground">
            {scoreMax.toFixed(3)}
          </span>
        </div>
        <div className="num text-[11px] text-foreground">
          {hovered
            ? `${hovered.a} × ${hovered.b} = ${hovered.score.toFixed(4)}`
            : <span className="marginalia text-muted-foreground/70">hover a cell</span>}
        </div>
      </div>
    </div>
  );
}
