import { useQuery } from '@tanstack/react-query';
import { ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';

import { SamplePreview } from './components/SamplePreview';

const sections = [
  { n: 'I', title: 'Method' },
  { n: 'II', title: 'Figure' },
  { n: 'III', title: 'Limitations' },
];

const steps = [
  {
    n: '01',
    title: 'Tokenize',
    body: 'Each numerical series is binned into a small alphabet over rolling windows.',
  },
  {
    n: '02',
    title: 'Self-surprise',
    body: 'The compressed length K(a) of a window’s own tokens stands in for its surprise.',
  },
  {
    n: '03',
    title: 'Mutual surprise',
    body: 'Concatenate two windows, compress again. The drop K(a)+K(b)−K(a‖b) measures shared structure.',
  },
  {
    n: '04',
    title: 'Null distribution',
    body: 'Random circular shifts destroy temporal alignment. Repeat to learn what surprise looks like by chance.',
  },
  {
    n: '05',
    title: 'False-discovery rate',
    body: 'Benjamini–Hochberg over per-edge p-values keeps the false-discovery rate beneath α.',
  },
];

function LiveDot() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: 30_000,
    retry: false,
  });
  const ok = !isError && data?.status === 'ok';
  return (
    <span className="inline-flex items-center gap-2">
      <span
        className={cn(
          'h-1.5 w-1.5 rounded-full',
          isLoading ? 'bg-mark animate-tick' : ok ? 'bg-sage' : 'bg-destructive',
        )}
      />
      <span className="marginalia">
        {isLoading ? 'Pinging' : ok ? 'API live' : 'API offline'}
      </span>
    </span>
  );
}

export function HomePage() {
  return (
    <>
      {/* ════════════════════════ TITLE PAGE ════════════════════════ */}
      <section className="container relative pb-16 pt-12 md:pb-24 md:pt-16">
        {/* Top metadata bar — like the running head of a printed page. */}
        <div className="mb-12 grid grid-cols-2 items-baseline gap-4 md:mb-20">
          <div className="marginalia">No. 001 · Anomaly Pipeline</div>
          <div className="marginalia text-right md:text-right">
            <LiveDot />
            <span className="ml-4 hidden text-muted-foreground/60 md:inline">
              May MMXXVI · Research preview
            </span>
          </div>
        </div>

        {/* Headline — asymmetric, hangs into the right column. */}
        <div className="grid grid-cols-12 gap-x-6 gap-y-8">
          <div className="col-span-12 md:col-span-9">
            <h1 className="display animate-ink-bleed text-display-1 text-foreground">
              Surprise,{' '}
              <span className="italic text-accent" style={{ fontVariationSettings: "'opsz' 144, 'WONK' 1, 'SOFT' 100" }}>
                across
              </span>{' '}
              domains.
            </h1>
          </div>
          <div className="col-span-12 md:col-span-3">
            {/* Editorial right rail — abstract-as-marginalia. */}
            <div
              className="animate-editorial-rise border-l border-border pl-4 [animation-delay:200ms]"
            >
              <div className="marginalia mb-2">Abstract</div>
              <p className="reading text-sm leading-snug text-muted-foreground">
                A compression-based read on whether two independent series fall
                strange together — and what fraction of that strangeness is
                merely chance.
              </p>
            </div>
          </div>
        </div>

        {/* Hairline + intro paragraph. */}
        <hr className="rule mt-16 origin-left animate-rule-draw [animation-delay:350ms]" />

        <div className="mt-10 grid grid-cols-12 gap-6">
          <div className="col-span-12 md:col-span-7">
            <p
              className="reading animate-editorial-rise text-xl leading-relaxed text-foreground/95 [animation-delay:450ms] md:text-2xl"
            >
              AMSG measures how surprising a window of geophysical data is by
              how poorly it compresses, then asks whether that surprise lands
              at the same moment in independent sources.{' '}
              <span className="italic text-muted-foreground">
                The result is a map of coupled rarity — a starting point, not a
                verdict.
              </span>
            </p>

            <div className="mt-10 flex flex-wrap items-center gap-4 animate-editorial-rise [animation-delay:600ms]">
              <Button asChild size="lg" variant="sienna">
                <Link to="/analyze?source=demo">
                  Run an analysis <ArrowUpRight />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <Link to="/docs">
                  Read the method <ArrowUpRight />
                </Link>
              </Button>
            </div>
          </div>

          {/* Right rail — running ToC. */}
          <aside className="col-span-12 md:col-span-4 md:col-start-9">
            <div className="marginalia mb-4">Contents</div>
            <ol className="space-y-2 border-l border-border pl-4">
              {sections.map((s) => (
                <li key={s.n} className="flex items-baseline gap-3 text-sm">
                  <span className="num text-muted-foreground/70">{s.n}</span>
                  <a href={`#sec-${s.n.toLowerCase()}`} className="hover:text-accent">
                    {s.title}
                  </a>
                </li>
              ))}
              <li className="flex items-baseline gap-3 text-sm">
                <span className="num text-muted-foreground/70">IV</span>
                <a href="/docs" className="hover:text-accent">
                  Full method →
                </a>
              </li>
            </ol>
          </aside>
        </div>
      </section>

      {/* ═══════════════════════ I. METHOD ═══════════════════════ */}
      <section id="sec-i" className="container scroll-mt-24 py-20 md:py-28">
        <div className="mb-12 grid grid-cols-12 gap-6">
          <div className="col-span-12 md:col-span-3">
            <div className="marginalia mb-1">§ I</div>
            <div className="num text-2xl text-accent md:text-3xl">01</div>
          </div>
          <div className="col-span-12 md:col-span-9">
            <h2 className="display text-display-2">Method, in five steps.</h2>
            <p className="reading mt-4 max-w-prose text-base text-muted-foreground md:text-lg">
              No trained models, no labeled anomalies. The whole pipeline runs
              on <span className="italic">numpy</span> and{' '}
              <span className="italic">zlib</span>; the score reduces to a few
              compression measurements and a permutation test.
            </p>
          </div>
        </div>

        <hr className="rule mb-2" />

        {/* Step list — printed-paper rows, hairline separators. */}
        <ol>
          {steps.map((s) => (
            <li
              key={s.n}
              className="group grid grid-cols-12 items-baseline gap-6 border-b border-border py-7 transition-colors hover:bg-foreground/[0.015]"
            >
              <div className="col-span-2 md:col-span-1">
                <span className="section-mark text-sm md:text-base">{s.n}</span>
              </div>
              <h3 className="col-span-10 text-xl tracking-tight md:col-span-3">
                <span className="display">{s.title}</span>
              </h3>
              <p className="reading col-span-12 max-w-prose text-base text-muted-foreground md:col-span-7 md:col-start-6 md:text-lg">
                {s.body}
              </p>
            </li>
          ))}
        </ol>

        {/* NMS formula — featured equation block. */}
        <figure className="mt-16 grid grid-cols-12 gap-6">
          <figcaption className="col-span-12 md:col-span-3">
            <div className="marginalia mb-1">Equation 1</div>
            <p className="reading text-sm text-muted-foreground">
              Normalized Mutual Surprise — the edge score for any window pair{' '}
              <span className="num text-foreground">a, b</span>.
            </p>
          </figcaption>
          <div className="col-span-12 md:col-span-9">
            <div className="border-y border-accent/40 py-10 text-center">
              <span className="num text-2xl tracking-tight md:text-4xl">
                NMS(a, b)
                <span className="mx-3 text-accent">=</span>
                <span className="text-accent">K(a) + K(b) − K(a‖b)</span>
                <span className="mx-3 text-muted-foreground">⁄</span>
                max{`{K(a), K(b)}`}
              </span>
            </div>
          </div>
        </figure>
      </section>

      {/* ═══════════════════════ II. FIGURE ═══════════════════════ */}
      <section id="sec-ii" className="container scroll-mt-24 py-20 md:py-28">
        <div className="mb-12 grid grid-cols-12 gap-6">
          <div className="col-span-12 md:col-span-3">
            <div className="marginalia mb-1">§ II</div>
            <div className="num text-2xl text-accent md:text-3xl">02</div>
          </div>
          <div className="col-span-12 md:col-span-9">
            <h2 className="display text-display-2">A figure, before it's a finding.</h2>
            <p className="reading mt-4 max-w-prose text-base text-muted-foreground md:text-lg">
              The Results dashboard renders synced subplots, an NMS heatmap
              across source pairs, a p-value histogram, and an events table you
              can filter and export to CSV. Below: a synthetic preview with a
              candidate event marked in sienna.
            </p>
          </div>
        </div>

        <figure>
          <div className="plate p-6 md:p-10">
            <SamplePreview />
          </div>
          <figcaption className="mt-3 flex items-baseline justify-between text-xs">
            <span className="marginalia">
              Fig. 1 · Synthetic series with a candidate event marked
            </span>
            <span className="marginalia text-muted-foreground/70">
              Recharts · Plotly
            </span>
          </figcaption>
        </figure>
      </section>

      {/* ════════════════════ III. LIMITATIONS ═══════════════════ */}
      <section id="sec-iii" className="container scroll-mt-24 py-20 md:py-28">
        <div className="mb-12 grid grid-cols-12 gap-6">
          <div className="col-span-12 md:col-span-3">
            <div className="marginalia mb-1">§ III</div>
            <div className="num text-2xl text-accent md:text-3xl">03</div>
          </div>
          <div className="col-span-12 md:col-span-9">
            <h2 className="display text-display-2">A negative result, kept honest.</h2>
          </div>
        </div>

        <div className="grid grid-cols-12 gap-6 md:gap-10">
          {/* Big "0 / 23" — the centerpiece. */}
          <div className="col-span-12 md:col-span-5">
            <div className="border-y border-accent/40 py-12 text-center md:py-16">
              <div className="num text-[clamp(5rem,15vw,12rem)] leading-none tracking-tight">
                <span className="text-accent">0</span>
                <span className="text-muted-foreground/40"> / </span>
                <span className="text-foreground">23</span>
              </div>
              <div className="marginalia mt-6">
                Replicated · over · candidate
              </div>
            </div>
          </div>

          <div className="col-span-12 md:col-span-7">
            <blockquote className="pull-quote text-foreground/95">
              <p>
                This is a tool for <em>hypothesis generation</em>, not
                validation. In our own evidence gate, no event survived
                shift-control replication.
              </p>
            </blockquote>
            <p className="reading mt-8 text-base leading-relaxed text-muted-foreground md:text-lg">
              AMSG is useful for surfacing windows worth inspecting — it is not
              a detector of confirmed phenomena. Two correlated bursts can be
              coincidence, common-cause, or instrumentation artefact.
              Compression-based novelty conflates real anomalies with format
              changes, sampling artefacts and clock errors. Read the{' '}
              <Link
                to="/docs#limitations"
                className="text-accent ink-underline"
              >
                limitations section
              </Link>{' '}
              before drawing conclusions from any output.
            </p>
          </div>
        </div>
      </section>

      {/* ════════════════════ FOOTER CTA ═══════════════════ */}
      <section className="container py-20 md:py-28">
        <hr className="rule mb-12" />
        <div className="grid grid-cols-12 gap-6 md:items-baseline">
          <div className="col-span-12 md:col-span-7">
            <h3 className="display text-display-3">
              Try the demo. No internet, no signup, no waiting.
            </h3>
            <p className="reading mt-3 text-base text-muted-foreground md:text-lg">
              The bundled <span className="num text-foreground">demo</span>{' '}
              source runs the pipeline on synthetic data offline, in seconds.
            </p>
          </div>
          <div className="col-span-12 md:col-span-5 md:text-right">
            <Button asChild size="lg" variant="ink">
              <Link to="/analyze?source=demo">
                Open the analyzer <ArrowUpRight />
              </Link>
            </Button>
          </div>
        </div>
      </section>
    </>
  );
}
