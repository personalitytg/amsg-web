import { ArrowUpDown, Eye, Search } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Slider } from '@/components/ui/slider';
import { cn } from '@/lib/utils';
import { formatNumber, formatPValue } from '@/lib/utils';
import type { AnomalyEvent } from '@/lib/types';

type SortKey = 'start' | 'best_p_value' | 'best_nms' | 'edge_novelty_sum';

export interface EventsTableProps {
  events: AnomalyEvent[];
  alpha: number;
  onOpen: (event: AnomalyEvent) => void;
  onHover?: (eventId: string | null) => void;
  onFilteredChange?: (events: AnomalyEvent[]) => void;
}

export function EventsTable({
  events,
  alpha,
  onOpen,
  onHover,
  onFilteredChange,
}: EventsTableProps) {
  const [sigOnly, setSigOnly] = useState(false);
  const [pMax, setPMax] = useState(1);
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('best_p_value');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const filtered = useMemo(() => {
    let out = events;
    if (sigOnly) {
      out = out.filter((e) => (e.q_value ?? e.best_p_value) <= alpha);
    }
    if (pMax < 1) {
      out = out.filter((e) => e.best_p_value <= pMax);
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      out = out.filter(
        (e) =>
          e.event_id.toLowerCase().includes(q) ||
          e.sources.some((s) => s.toLowerCase().includes(q)) ||
          e.domains.some((d) => d.toLowerCase().includes(q)),
      );
    }
    out = [...out].sort((a, b) => {
      const va = (a[sortKey] as number | string) ?? 0;
      const vb = (b[sortKey] as number | string) ?? 0;
      const cmp = va < vb ? -1 : va > vb ? 1 : 0;
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return out;
  }, [events, sigOnly, pMax, search, sortKey, sortDir, alpha]);

  useEffect(() => {
    onFilteredChange?.(filtered);
  }, [filtered, onFilteredChange]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  return (
    <div className="space-y-6">
      {/* Filters bar — editorial: hairline-divided, marginalia labels. */}
      <div className="grid grid-cols-1 gap-4 border-y border-border py-4 md:grid-cols-3">
        <label className="flex items-center gap-3">
          <Checkbox
            checked={sigOnly}
            onChange={(e) => setSigOnly(e.currentTarget.checked)}
          />
          <span className="marginalia">Significant only · q ≤ α</span>
        </label>
        <div className="flex items-baseline gap-3">
          <span className="marginalia shrink-0">p ≤</span>
          <Slider
            min={0.001}
            max={1}
            step={0.005}
            value={pMax}
            onChange={(e) => setPMax(Number(e.currentTarget.value))}
          />
          <span className="num w-12 shrink-0 text-right text-xs">{pMax.toFixed(2)}</span>
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute left-1 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder="filter by id / source / domain"
            value={search}
            onChange={(e) => setSearch(e.currentTarget.value)}
            className="h-9 pl-6"
          />
        </div>
      </div>

      <div className="overflow-hidden">
        <div className="max-h-[520px] overflow-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 z-10 bg-background">
              <tr className="border-b border-border">
                <Th>event</Th>
                <Th onClick={() => toggleSort('start')}>
                  range <ArrowUpDown className="inline h-3 w-3" />
                </Th>
                <Th className="text-right" onClick={() => toggleSort('best_p_value')}>
                  p <ArrowUpDown className="inline h-3 w-3" />
                </Th>
                <Th className="text-right">q</Th>
                <Th className="text-right" onClick={() => toggleSort('best_nms')}>
                  NMS <ArrowUpDown className="inline h-3 w-3" />
                </Th>
                <Th className="text-right" onClick={() => toggleSort('edge_novelty_sum')}>
                  novelty <ArrowUpDown className="inline h-3 w-3" />
                </Th>
                <Th>sources</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center italic text-muted-foreground">
                    No events match the current filters.
                  </td>
                </tr>
              ) : (
                filtered.map((e) => {
                  const sig = (e.q_value ?? e.best_p_value) <= alpha;
                  return (
                    <tr
                      key={e.event_id}
                      onMouseEnter={() => onHover?.(e.event_id)}
                      onMouseLeave={() => onHover?.(null)}
                      className={cn(
                        'border-b border-border/40 transition-colors',
                        'hover:bg-foreground/[0.02]',
                        sig && 'bg-accent/[0.04]',
                      )}
                    >
                      <td className="num py-3 pr-3">
                        {e.event_id}
                        {e.is_holdout && (
                          <Badge variant="accent" className="ml-1.5">
                            holdout
                          </Badge>
                        )}
                      </td>
                      <td className="num whitespace-nowrap py-3 pr-3 text-[10px] text-muted-foreground">
                        {e.start.replace('T', ' ')}
                        <br />
                        {e.end.replace('T', ' ')}
                      </td>
                      <td className="num py-3 pr-3 text-right">{formatPValue(e.best_p_value)}</td>
                      <td className="num py-3 pr-3 text-right">{formatPValue(e.q_value)}</td>
                      <td className="num py-3 pr-3 text-right">{formatNumber(e.best_nms, 3)}</td>
                      <td className="num py-3 pr-3 text-right">
                        {formatNumber(e.edge_novelty_sum, 2)}
                      </td>
                      <td className="py-3 pr-3">
                        <div className="flex flex-wrap gap-1">
                          {e.sources.slice(0, 3).map((s) => (
                            <Badge key={s} variant="outline">
                              {s}
                            </Badge>
                          ))}
                          {e.sources.length > 3 && (
                            <span className="num text-[10px] text-muted-foreground">
                              +{e.sources.length - 3}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 text-right">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 px-2"
                          onClick={() => onOpen(e)}
                        >
                          <Eye className="h-3.5 w-3.5" />
                        </Button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Th({
  children,
  onClick,
  className,
}: {
  children?: ReactNode;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <th
      onClick={onClick}
      className={cn(
        'px-3 py-2 text-left font-mono text-[10px] font-medium uppercase tracking-[0.16em] text-muted-foreground',
        onClick && 'cursor-pointer select-none hover:text-accent',
        className,
      )}
    >
      {children}
    </th>
  );
}
