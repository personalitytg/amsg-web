import { Badge } from '@/components/ui/badge';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { formatNumber, formatPValue } from '@/lib/utils';
import type { AnomalyEvent } from '@/lib/types';

export interface EventDetailSheetProps {
  event: AnomalyEvent | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  alpha: number;
}

export function EventDetailSheet({ event, open, onOpenChange, alpha }: EventDetailSheetProps) {
  if (!event) return null;
  const isSig = (event.q_value ?? event.best_p_value) <= alpha;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent>
        <SheetHeader>
          <div className="marginalia">Event detail</div>
          <SheetTitle className="display num text-xl">{event.event_id}</SheetTitle>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={isSig ? 'success' : 'outline'}>
              {isSig ? 'Significant' : 'Below threshold'}
            </Badge>
            {event.is_holdout && <Badge variant="accent">Holdout</Badge>}
          </div>
          <SheetDescription className="num text-xs">
            {event.start} → {event.end}
          </SheetDescription>
        </SheetHeader>

        <hr className="rule" />

        <div className="grid grid-cols-2 gap-x-6 gap-y-5">
          <Stat label="best p" value={formatPValue(event.best_p_value)} />
          <Stat label="q · BH" value={formatPValue(event.q_value)} />
          <Stat label="best NMS" value={formatNumber(event.best_nms, 4)} />
          <Stat label="novelty Σ" value={formatNumber(event.edge_novelty_sum, 3)} />
          <Stat label="edges" value={String(event.edges_count)} />
          <Stat label="cross-domain" value={String(event.cross_domain_edges_count)} />
        </div>

        <div className="space-y-2">
          <div className="marginalia">Sources & domains</div>
          <div className="flex flex-wrap gap-1.5">
            {event.sources.map((s) => (
              <Badge key={s} variant="default">
                {s}
              </Badge>
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {event.domains.map((d) => (
              <Badge key={d} variant="secondary">
                {d}
              </Badge>
            ))}
          </div>
        </div>

        <div className="min-h-0 flex-1 space-y-2 overflow-hidden">
          <div className="marginalia">Top edges</div>
          <div className="overflow-y-auto border-y border-border">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-background">
                <tr className="border-b border-border">
                  <th className="num py-2 pr-2 text-left text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                    a
                  </th>
                  <th className="num py-2 pr-2 text-left text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                    b
                  </th>
                  <th className="num py-2 pr-2 text-right text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                    NMS
                  </th>
                  <th className="num py-2 pr-2 text-right text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                    p
                  </th>
                  <th className="num py-2 pr-2 text-right text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                    novelty
                  </th>
                </tr>
              </thead>
              <tbody>
                {event.top_edges.length === 0 ? (
                  <tr>
                    <td className="py-3 text-center italic text-muted-foreground" colSpan={5}>
                      No edges recorded.
                    </td>
                  </tr>
                ) : (
                  event.top_edges.map((e, i) => (
                    <tr
                      key={`${e.a}-${e.b}-${i}`}
                      className="border-b border-border/40 hover:bg-foreground/[0.02]"
                    >
                      <td className="num py-2 pr-2">{e.a}</td>
                      <td className="num py-2 pr-2">{e.b}</td>
                      <td className="num py-2 pr-2 text-right">{formatNumber(e.nms, 4)}</td>
                      <td className="num py-2 pr-2 text-right">{formatPValue(e.p_value)}</td>
                      <td className="num py-2 pr-2 text-right">{formatNumber(e.novelty, 3)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-l border-border pl-3">
      <div className="marginalia">{label}</div>
      <div className="num mt-1 text-base">{value}</div>
    </div>
  );
}
