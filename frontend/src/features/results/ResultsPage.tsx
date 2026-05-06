import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Download, FileJson } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { api, ApiError, subscribeProgress } from '@/lib/api';
import type {
  AnalysisResult,
  AnomalyEvent,
  JobEnvelope,
  JobProgress,
  JobStatus,
} from '@/lib/types';
import { useAnalysisHistory } from '@/stores/analysisHistory';

import { EventDetailSheet } from './components/EventDetailSheet';
import { EventsTable } from './components/EventsTable';
import { HeatmapPanel } from './components/HeatmapPanel';
import { HeroMetrics } from './components/HeroMetrics';
import { ProgressCardLite } from './components/ProgressCardLite';
import { PValueHistogram } from './components/PValueHistogram';
import { SeriesChart } from './components/SeriesChart';
import { downloadEventsCsv, downloadResultJson } from './lib/export';

export function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const updateHistory = useAnalysisHistory((s) => s.update);

  const query = useQuery<JobEnvelope, ApiError>({
    queryKey: ['analysis', id],
    queryFn: () => api.getAnalysis(id!),
    enabled: Boolean(id),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === 'succeeded' || s === 'failed' ? false : 2000;
    },
    retry: (count, err) => {
      if (err instanceof ApiError && err.status === 404) return false;
      return count < 2;
    },
  });

  const [liveProgress, setLiveProgress] = useState<JobProgress | null>(null);
  const [liveStatus, setLiveStatus] = useState<JobStatus | null>(null);
  const unsubRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!id) return;
    if (!query.data) return;
    const status = query.data.status;
    if (status !== 'pending' && status !== 'running') return;

    unsubRef.current?.();
    unsubRef.current = subscribeProgress(
      id,
      (msg) => {
        setLiveProgress({ stage: msg.stage, percent: msg.percent, message: msg.message });
        if (msg.status) setLiveStatus(msg.status as JobStatus);
      },
      (info) => {
        const final = (info.status as JobStatus) ?? 'succeeded';
        setLiveStatus(final);
        updateHistory(id, { status: final });
        query.refetch();
      },
    );
    return () => {
      unsubRef.current?.();
    };
  }, [id, query.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!id) {
    return (
      <article className="container py-24">
        <div className="mx-auto max-w-md">
          <div className="marginalia mb-2">No job id</div>
          <h1 className="display text-display-3">Submit a new analysis to see a result here.</h1>
          <Button asChild variant="sienna" className="mt-6">
            <Link to="/analyze">
              <ArrowLeft className="h-4 w-4" />
              Go to Analyze
            </Link>
          </Button>
        </div>
      </article>
    );
  }

  if (query.isLoading) {
    return (
      <article className="container space-y-4 py-16">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-72 w-full" />
      </article>
    );
  }

  if (query.isError) {
    const expired = query.error instanceof ApiError && query.error.status === 404;
    return (
      <article className="container py-24">
        <div className="mx-auto max-w-2xl">
          <div className="marginalia mb-2 text-mark">Notice</div>
          <h1 className="display text-display-3">
            {expired ? 'Job expired.' : 'Could not load job.'}
          </h1>
          <p className="reading mt-4 text-base text-muted-foreground md:text-lg">
            {expired
              ? 'Job state lives in memory — restarting the backend evicts it. Submit a fresh analysis to continue.'
              : query.error.detail}
          </p>
          <div className="mt-8 flex gap-3">
            <Button asChild variant="sienna">
              <Link to="/analyze">
                <ArrowLeft className="h-4 w-4" />
                Run a new analysis
              </Link>
            </Button>
            <Button variant="outline" onClick={() => query.refetch()}>
              Retry
            </Button>
          </div>
        </div>
      </article>
    );
  }

  const env = query.data;
  if (!env) return null;
  const status: JobStatus = liveStatus ?? env.status;
  const progress: JobProgress = liveProgress ?? env.progress;

  if (status !== 'succeeded' && status !== 'failed') {
    return (
      <article className="container py-12 md:py-16">
        <header className="mb-12">
          <div className="marginalia mb-3">Tracking job</div>
          <h1 className="display text-display-2">Analysis in progress.</h1>
          <p className="num mt-2 text-sm text-muted-foreground">
            {env.id}
          </p>
        </header>
        <ProgressCardLite jobId={env.id} status={status} progress={progress} />
      </article>
    );
  }

  if (status === 'failed') {
    return (
      <article className="container py-16">
        <div className="mx-auto max-w-2xl">
          <div className="marginalia mb-2 text-destructive">Run failed</div>
          <h1 className="display text-display-3">Analysis failed.</h1>
          <pre className="mt-6 overflow-x-auto border border-destructive/40 bg-destructive/[0.04] p-4 text-xs text-destructive">
            {env.error || 'Unknown error.'}
          </pre>
          <Button asChild variant="sienna" className="mt-6">
            <Link to="/analyze">
              <ArrowLeft className="h-4 w-4" />
              Back to Analyze
            </Link>
          </Button>
        </div>
      </article>
    );
  }

  const result = env.result;
  if (!result) {
    return (
      <article className="container py-16">
        <p className="text-sm text-muted-foreground">
          Job is succeeded but the payload is empty — this should not happen.
        </p>
      </article>
    );
  }

  const alpha = (result.config_echo?.alpha as number | undefined) ?? 0.05;
  return <ResultsDashboard env={env} result={result} alpha={alpha} />;
}

interface DashboardProps {
  env: JobEnvelope;
  result: AnalysisResult;
  alpha: number;
}

function ResultsDashboard({ env, result, alpha }: DashboardProps) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [active, setActive] = useState<AnomalyEvent | null>(null);
  const [filtered, setFiltered] = useState<AnomalyEvent[]>(result.events);

  const exportCsv = () => {
    if (filtered.length === 0) {
      toast.message('Nothing to export with current filters.');
      return;
    }
    downloadEventsCsv(filtered, env.id);
  };
  const exportJson = () => downloadResultJson(result);

  const sourceLabels = useMemo(
    () =>
      Object.fromEntries(result.series.map((s) => [s.source_id, s.label])) as Record<string, string>,
    [result.series],
  );

  return (
    <article className="container py-12 md:py-16">
      {/* Title page */}
      <header className="mb-12 grid grid-cols-12 gap-6">
        <div className="col-span-12 md:col-span-9">
          <div className="marginalia mb-3 text-sage">Run complete</div>
          <h1 className="display text-display-2">
            Analysis results.
          </h1>
          <p className="num mt-3 text-xs text-muted-foreground md:text-sm">
            Job {env.id} · α = {alpha} ·{' '}
            <Link
              to="/analyze"
              className="text-accent ink-underline"
            >
              new analysis
            </Link>
          </p>
        </div>
        <div className="col-span-12 flex flex-wrap items-center gap-2 md:col-span-3 md:justify-end">
          <Button variant="outline" size="sm" onClick={exportCsv}>
            <Download className="h-3.5 w-3.5" />
            CSV
          </Button>
          <Button variant="outline" size="sm" onClick={exportJson}>
            <FileJson className="h-3.5 w-3.5" />
            JSON
          </Button>
        </div>
      </header>

      <hr className="rule mb-12" />

      {/* Hero metrics — inline figures */}
      <HeroMetrics summary={result.summary} alpha={alpha} />

      {/* §I — Time series */}
      <section className="mt-20 grid grid-cols-12 gap-6">
        <div className="col-span-12 md:col-span-3">
          <div className="marginalia mb-1">§ I · Figure 1</div>
          <h2 className="display text-2xl">Series over time.</h2>
          <p className="reading mt-2 text-sm text-muted-foreground">
            Synced subplots, one row per source. Sienna bands mark candidate
            events; cyan rule shows the row hovered in the table.
          </p>
        </div>
        <div className="col-span-12 md:col-span-9">
          <div className="border-y border-border py-6">
            <SeriesChart
              series={result.series}
              events={result.events}
              alpha={alpha}
              highlightedEventId={hovered}
            />
          </div>
        </div>
      </section>

      {/* §II — Heatmap & p-values */}
      <section className="mt-20 grid grid-cols-12 gap-6">
        <div className="col-span-12 md:col-span-3">
          <div className="marginalia mb-1">§ II · Figures 2 & 3</div>
          <h2 className="display text-2xl">Pair structure & p-values.</h2>
          <p className="reading mt-2 text-sm text-muted-foreground">
            Heatmap reads median NMS per pair. Histogram reads the p-value
            distribution; the dashed sienna rule marks α.
          </p>
        </div>
        <div className="col-span-12 grid grid-cols-1 gap-12 md:col-span-9 md:grid-cols-2">
          <figure>
            <div className="border-y border-border py-6">
              <HeatmapPanel cells={result.heatmap} />
            </div>
            <figcaption className="marginalia mt-3">
              Fig. 2 · Median NMS per source pair
            </figcaption>
          </figure>
          <figure>
            <div className="border-y border-border py-6">
              <PValueHistogram buckets={result.p_value_histogram} alpha={alpha} />
            </div>
            <figcaption className="marginalia mt-3">
              Fig. 3 · p-value distribution · α = {alpha}
            </figcaption>
          </figure>
        </div>
      </section>

      {/* §III — Events table */}
      <section className="mt-20 grid grid-cols-12 gap-6">
        <div className="col-span-12 md:col-span-3">
          <div className="marginalia mb-1">§ III · Table I</div>
          <h2 className="display text-2xl">Candidate events.</h2>
          <p className="reading mt-2 text-sm text-muted-foreground">
            Click a row to inspect contributing edges. Filtered rows define
            what CSV export emits.
          </p>
          <div className="num mt-4 text-xs text-muted-foreground">
            {result.events.length} events · {filtered.length} filtered
          </div>
        </div>
        <div className="col-span-12 md:col-span-9">
          <EventsTable
            events={result.events}
            alpha={alpha}
            onOpen={setActive}
            onHover={setHovered}
            onFilteredChange={setFiltered}
          />
        </div>
      </section>

      {/* Source legend */}
      {Object.keys(sourceLabels).length > 0 && (
        <section className="mt-16">
          <hr className="rule mb-4" />
          <div className="marginalia mb-3">Source legend</div>
          <ul className="grid grid-cols-1 gap-2 text-sm md:grid-cols-2 lg:grid-cols-3">
            {Object.entries(sourceLabels).map(([id, label]) => (
              <li key={id} className="flex items-baseline gap-2">
                <span className="num text-xs text-accent">{id}</span>
                <span className="text-muted-foreground">— {label}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <EventDetailSheet
        event={active}
        open={!!active}
        onOpenChange={(o) => !o && setActive(null)}
        alpha={alpha}
      />
    </article>
  );
}
