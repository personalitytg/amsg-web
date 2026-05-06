import { useQuery } from '@tanstack/react-query';
import { format, subDays } from 'date-fns';
import { ArrowUpRight } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { type DateRange } from 'react-day-picker';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { api, subscribeProgress } from '@/lib/api';
import type {
  AnalyzeRequest,
  AnalyzeSettings,
  JobProgress,
  JobStatus,
} from '@/lib/types';
import { useAnalysisHistory } from '@/stores/analysisHistory';

import { DateRangePicker } from './components/DateRangePicker';
import { HistorySidebar } from './components/HistorySidebar';
import { ProgressCard } from './components/ProgressCard';
import { SettingsPanel, DEFAULT_SETTINGS } from './components/SettingsPanel';
import { SourceSelect } from './components/SourceSelect';
import { useStartAnalysis } from './hooks/useStartAnalysis';

interface ActiveJob {
  jobId: string;
  status: JobStatus;
  progress: JobProgress;
  error: string | null;
}

const initialProgress: JobProgress = { stage: 'queued', percent: 0, message: 'Queued' };

function isoDate(d: Date): string {
  return format(d, 'yyyy-MM-dd');
}

function isRunning(active: ActiveJob | null) {
  return active?.status === 'pending' || active?.status === 'running';
}

interface FieldsetProps {
  number: string;
  title: string;
  hint?: string;
  children: React.ReactNode;
}

function Fieldset({ number, title, hint, children }: FieldsetProps) {
  return (
    <section className="border-t border-border py-10 first:border-t-0 first:pt-0">
      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 md:col-span-3">
          <div className="marginalia mb-1">{number}</div>
          <h2 className="display text-2xl text-foreground">{title}</h2>
          {hint && (
            <p className="reading mt-2 text-sm text-muted-foreground">{hint}</p>
          )}
        </div>
        <div className="col-span-12 md:col-span-9">{children}</div>
      </div>
    </section>
  );
}

export function AnalyzePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const sourcesQuery = useQuery({ queryKey: ['sources'], queryFn: api.listSources });
  const addHistory = useAnalysisHistory((s) => s.add);
  const updateHistory = useAnalysisHistory((s) => s.update);

  const [selected, setSelected] = useState<string[]>([]);
  const [range, setRange] = useState<DateRange | undefined>(() => {
    const today = new Date();
    return { from: subDays(today, 6), to: today };
  });
  const [settings, setSettings] = useState<AnalyzeSettings>(DEFAULT_SETTINGS);
  const [label, setLabel] = useState('');

  const [active, setActive] = useState<ActiveJob | null>(null);
  const unsubRef = useRef<(() => void) | null>(null);

  const presetApplied = useRef(false);
  useEffect(() => {
    if (presetApplied.current) return;
    if (!sourcesQuery.data) return;
    const want = searchParams.get('source');
    if (want) {
      const exists = sourcesQuery.data.sources.find(
        (s) => s.id === want && s.status === 'available',
      );
      if (exists) setSelected([want]);
    }
    presetApplied.current = true;
  }, [searchParams, sourcesQuery.data]);

  useEffect(() => {
    return () => {
      unsubRef.current?.();
    };
  }, []);

  const startMutation = useStartAnalysis({
    onSuccess: (data, vars) => {
      const labelText =
        vars.label || `${vars.source_ids.join('+')} · ${vars.start} → ${vars.end}`;
      addHistory({
        jobId: data.job_id,
        label: labelText,
        startedAt: Date.now(),
        sourceIds: vars.source_ids,
        status: 'pending',
      });
      setActive({
        jobId: data.job_id,
        status: data.status,
        progress: initialProgress,
        error: null,
      });

      unsubRef.current?.();
      unsubRef.current = subscribeProgress(
        data.job_id,
        (msg) => {
          setActive((prev) =>
            prev && prev.jobId === data.job_id
              ? {
                  ...prev,
                  status: (msg.status as JobStatus) ?? prev.status,
                  progress: { stage: msg.stage, percent: msg.percent, message: msg.message },
                }
              : prev,
          );
        },
        (info) => {
          const finalStatus = (info.status as JobStatus) ?? 'succeeded';
          setActive((prev) =>
            prev && prev.jobId === data.job_id
              ? { ...prev, status: finalStatus, error: info.error }
              : prev,
          );
          updateHistory(data.job_id, { status: finalStatus });
          if (finalStatus === 'succeeded') {
            toast.success('Analysis complete');
            setTimeout(() => navigate(`/results/${data.job_id}`), 600);
          } else {
            toast.error(`Analysis ${finalStatus}: ${info.error ?? 'unknown error'}`);
          }
        },
        () => {
          toast.error('Lost progress connection');
        },
      );
    },
  });

  const validation = useMemo(() => {
    const errs: string[] = [];
    if (selected.length === 0) errs.push('Select at least one source.');
    if (!range?.from || !range?.to) errs.push('Pick a start and end date.');
    if (range?.from && range.to && range.from > range.to)
      errs.push('Start date must be before end date.');
    return errs;
  }, [selected, range]);

  const canSubmit = validation.length === 0 && !startMutation.isPending && !isRunning(active);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!range?.from || !range.to) return;
    const req: AnalyzeRequest = {
      source_ids: selected,
      start: isoDate(range.from),
      end: isoDate(range.to),
      settings,
      label: label.trim() || undefined,
    };
    startMutation.mutate(req);
  };

  return (
    <article className="container py-12 md:py-16">
      <div className="grid grid-cols-12 gap-x-6 gap-y-12">
        <div className="col-span-12 lg:col-span-9">
          {/* Title page header */}
          <header className="mb-12">
            <div className="marginalia mb-3">Procedure · Run No. {Date.now().toString(36).slice(-4)}</div>
            <h1 className="display text-display-2">
              Configure an{' '}
              <span className="italic text-accent" style={{ fontVariationSettings: "'opsz' 144, 'WONK' 1, 'SOFT' 100" }}>
                analysis.
              </span>
            </h1>
            <p className="reading mt-4 max-w-prose text-base text-muted-foreground md:text-lg">
              Pick sources, a window of time, and pipeline knobs. Submission is
              asynchronous — you will be redirected to the results dashboard
              the moment it finishes.
            </p>
          </header>

          {active && (
            <div className="mb-12">
              <ProgressCard
                jobId={active.jobId}
                status={active.status}
                progress={active.progress}
                error={active.error}
              />
            </div>
          )}

          <hr className="rule mb-10" />

          <form onSubmit={onSubmit}>
            <Fieldset
              number="§ 01 · Sources"
              title="Pick at least one source."
              hint="Demo runs offline; live sources fetch from external APIs and may take longer."
            >
              <SourceSelect
                sources={sourcesQuery.data?.sources}
                isLoading={sourcesQuery.isLoading}
                isError={sourcesQuery.isError}
                selected={selected}
                onChange={setSelected}
              />
            </Fieldset>

            <Fieldset
              number="§ 02 · Time range"
              title="Inclusive ISO dates."
              hint="Defaults to the last seven days; pick a tighter or wider window as needed."
            >
              <div className="space-y-6">
                <DateRangePicker value={range} onChange={setRange} />
                <div>
                  <Label htmlFor="label" className="marginalia mb-1.5 block">
                    Run label · optional
                  </Label>
                  <Input
                    id="label"
                    value={label}
                    onChange={(e) => setLabel(e.currentTarget.value)}
                    placeholder="e.g. May Kp-storm preview"
                    maxLength={64}
                  />
                </div>
              </div>
            </Fieldset>

            <Fieldset
              number="§ 03 · Pipeline settings"
              title="Tune the knobs."
              hint="Sensible defaults are pre-set; tighten the FDR target or null-shift count to trade speed for sharper p-values."
            >
              <SettingsPanel settings={settings} onChange={setSettings} />
            </Fieldset>

            {validation.length > 0 && (
              <div className="border-l-2 border-mark py-4 pl-4 text-sm text-mark">
                <ul className="space-y-1">
                  {validation.map((v) => (
                    <li key={v}>· {v}</li>
                  ))}
                </ul>
              </div>
            )}

            <hr className="rule my-10" />

            <div className="flex items-center justify-end gap-3">
              <Button type="submit" size="lg" variant="sienna" disabled={!canSubmit}>
                {startMutation.isPending ? 'Submitting…' : 'Run analysis'}
                <ArrowUpRight />
              </Button>
            </div>
          </form>
        </div>

        <HistorySidebar />
      </div>
    </article>
  );
}
