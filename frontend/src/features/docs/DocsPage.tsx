import { ArrowUpRight } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { cn } from '@/lib/utils';

interface SectionDef {
  id: string;
  number: string;
  title: string;
}

const sections: SectionDef[] = [
  { id: 'why-compression', number: 'I', title: 'Why compression' },
  { id: 'nms', number: 'II', title: 'The NMS formula' },
  { id: 'pipeline', number: 'III', title: 'Pipeline' },
  { id: 'null-fdr', number: 'IV', title: 'Null & FDR' },
  { id: 'controls', number: 'V', title: 'Negative controls' },
  { id: 'limitations', number: 'VI', title: 'Limitations' },
  { id: 'api', number: 'VII', title: 'API reference' },
];

function Section({
  id,
  number,
  title,
  lead,
  children,
}: {
  id: string;
  number: string;
  title: string;
  lead?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24 border-b border-border/60 py-16 md:py-24">
      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 md:col-span-3">
          <div className="marginalia mb-1">§ {number}</div>
          <div className="num text-2xl text-accent md:text-3xl">{number}</div>
        </div>
        <div className="col-span-12 md:col-span-9">
          <h2 className="display text-display-2">{title}</h2>
          {lead && (
            <p className="reading mt-4 max-w-prose text-base text-muted-foreground md:text-lg">
              {lead}
            </p>
          )}
        </div>
      </div>
      <div className="mt-8 grid grid-cols-12 gap-6">
        <div className="col-span-12 md:col-span-9 md:col-start-4">
          <div className="reading max-w-prose space-y-5 text-base leading-relaxed text-foreground/90 md:text-lg">
            {children}
          </div>
        </div>
      </div>
    </section>
  );
}

function Code({ children }: { children: ReactNode }) {
  return (
    <code className="num rounded-none border-b border-accent/40 px-0.5 text-[0.95em] text-foreground">
      {children}
    </code>
  );
}

function FootNote({ marker, children }: { marker: string; children: ReactNode }) {
  return (
    <aside className="my-6 grid grid-cols-12 gap-4 border-l border-accent/40 pl-4">
      <div className="col-span-1">
        <span className="marginalia text-accent">{marker}</span>
      </div>
      <p className="col-span-11 text-sm italic text-muted-foreground">{children}</p>
    </aside>
  );
}

export function DocsPage() {
  return (
    <article className="container py-16 md:py-24">
      {/* TITLE PAGE */}
      <header className="grid grid-cols-12 gap-6 pb-12">
        <div className="col-span-12 md:col-span-9">
          <div className="marginalia mb-4">
            Monograph · No. 002 · Method
          </div>
          <h1 className="display text-display-1">
            On the strangeness{' '}
            <span className="italic text-accent" style={{ fontVariationSettings: "'opsz' 144, 'WONK' 1, 'SOFT' 100" }}>
              of windows.
            </span>
          </h1>
          <p className="reading mt-6 max-w-prose text-lg text-muted-foreground md:text-xl">
            What AMSG computes, what each knob does, and why the honest answer
            to <span className="italic">does it find anomalies?</span> is{' '}
            <span className="italic">sometimes, candidates; never,
            confirmations.</span>
          </p>
        </div>
      </header>

      <hr className="rule mb-16" />

      <div className="grid grid-cols-12 gap-x-6">
        {/* Marginalia TOC — sticky on lg+. */}
        <aside className="hidden md:col-span-3 md:block">
          <div className="sticky top-24">
            <div className="marginalia mb-4">Contents</div>
            <ol className="space-y-2">
              {sections.map((s) => (
                <li key={s.id} className="flex items-baseline gap-3 text-sm">
                  <span className="num text-muted-foreground/70">{s.number}</span>
                  <a
                    href={`#${s.id}`}
                    className="text-muted-foreground transition-colors hover:text-accent"
                  >
                    {s.title}
                  </a>
                </li>
              ))}
            </ol>
            <hr className="rule my-6" />
            <div className="marginalia mb-2">Apparatus</div>
            <ul className="space-y-1.5 text-sm">
              <li>
                <a className="text-muted-foreground hover:text-accent" href="/api/docs">
                  Swagger / OpenAPI
                </a>
              </li>
              <li>
                <a
                  className="text-muted-foreground hover:text-accent"
                  href="https://github.com/"
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  Source repository
                </a>
              </li>
            </ul>
          </div>
        </aside>

        {/* BODY */}
        <div className="col-span-12 md:col-span-9">
          <Section
            id="why-compression"
            number="I"
            title="Why compression?"
            lead="A window of bytes compresses well exactly when it is regular: repeating patterns, predictable autocorrelation, low effective entropy. A window compresses badly when it is novel — when its structure breaks from what came before."
          >
            <p>
              <span className="reading float-left mr-2 mt-1 text-7xl leading-[0.85] text-accent" style={{ fontVariationSettings: "'opsz' 144, 'WONK' 1, 'SOFT' 100" }}>
                T
              </span>
              his makes compressed length a cheap proxy for <em>surprise</em>,
              with no model to train and no labels to gather. AMSG bins each
              numerical sample into a small alphabet via rolling quantiles,
              then uses <Code>zlib</Code> on the resulting symbol stream.
            </p>
            <p>
              The compressed length <Code>K(a)</Code> is the self-surprise of
              window <Code>a</Code>. By concatenating two windows from
              different sources and compressing again, we get{' '}
              <Code>K(a‖b)</Code> — the surprise of <Code>a</Code> conditioned
              on having already seen <Code>b</Code>.
            </p>
          </Section>

          <Section
            id="nms"
            number="II"
            title="The NMS formula"
            lead="We define the Normalized Mutual Surprise between two windows as the fraction of joint surprise that disappears when they are seen together, normalized by the larger of the two."
          >
            <figure className="my-8 border-y border-accent/40 py-8 text-center">
              <span className="num text-xl tracking-tight md:text-2xl">
                NMS(a, b)
                <span className="mx-2 text-accent">=</span>
                <span className="text-accent">K(a) + K(b) − K(a‖b)</span>
                <span className="mx-2 text-muted-foreground">⁄</span>
                max{`{K(a), K(b)}`}
              </span>
              <figcaption className="marginalia mt-4">
                Equation 1 · Normalized Mutual Surprise
              </figcaption>
            </figure>
            <p>
              <Code>NMS</Code> is bounded in <Code>[0, 1]</Code> in practice —
              negative values indicate compression overhead and are clamped.
              High NMS means the two windows share structure that compression
              can exploit, a sign of coupled behaviour.
            </p>
            <p>
              The pipeline scores every pair of windows from every pair of
              sources. Each window-pair gets one NMS value; aggregations across
              windows produce the heatmap on the Results page.
            </p>
          </Section>

          <Section
            id="pipeline"
            number="III"
            title="Pipeline"
            lead="Five steps. No trained models, no labeled anomalies."
          >
            <ol className="not-prose ml-0 list-none space-y-4">
              {[
                ['Tokenize', 'Bin each series into a small alphabet over rolling windows. Defaults: window sizes [64, 128, 256].'],
                ['Self-surprise', 'Compute K(a) = len(zlib(a)) for every window of every source.'],
                ['Mutual surprise', 'For every pair, compute K(a‖b) and the NMS score.'],
                ['Null distribution', 'Apply random circular shifts (block size shift_d) to break alignment, re-score; repeat null_shifts_count times to estimate per-edge p-values.'],
                ['FDR', 'Apply Benjamini–Hochberg across all edge p-values to control the false-discovery rate at alpha.'],
              ].map(([title, body], i) => (
                <li key={title} className="grid grid-cols-12 gap-3 border-l border-border pl-4">
                  <span className="num col-span-1 text-accent">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <div className="col-span-11">
                    <div className="display text-lg">{title}</div>
                    <p className="text-base text-muted-foreground">{body}</p>
                  </div>
                </li>
              ))}
            </ol>
            <p>
              Events are formed by clustering surviving edges along the time
              axis, then ranked by their best p-value, q-value, and
              contributing novelty.
            </p>
          </Section>

          <Section
            id="null-fdr"
            number="IV"
            title="Null distribution & FDR"
            lead="Without a baseline, NMS is just a number. The null distribution gives it meaning."
          >
            <p>
              We destroy any cross-source temporal alignment by circularly
              shifting one stream by a random offset, then recompute every
              score. Any structure that survives is presumably accidental.
            </p>
            <p>
              The result is a per-edge empirical p-value: the fraction of null
              shifts that produced an NMS at least as extreme as the observed
              one. With many edges, naïve thresholding inflates the
              false-discovery rate, so we apply Benjamini–Hochberg correction
              at level <Code>alpha</Code> (default <Code>0.05</Code>) to
              obtain q-values.
            </p>
            <FootNote marker="*">
              The Results page renders a p-value distribution chart with a
              dashed line at <Code>alpha</Code>; events with{' '}
              <Code>q ≤ alpha</Code> are marked significant.
            </FootNote>
          </Section>

          <Section
            id="controls"
            number="V"
            title="Negative controls"
            lead="The pipeline ships with two opt-in sanity checks. Passing them is a low bar — they are guard-rails against obvious failure modes, not endorsements of any candidate."
          >
            <p>
              <span className="display text-lg">Shift control. </span>
              A holdout fraction of trailing windows (configurable via{' '}
              <Code>holdout_ratio</Code>) is set aside; significant events are
              only counted as <em>replicated</em> if they re-emerge in the
              holdout under independent shifts.
            </p>
            <p>
              <span className="display text-lg">Out-of-domain control. </span>
              Running the pipeline on series deliberately unrelated to the
              phenomenon under study (e.g. BTC volume against solar wind)
              should produce zero significant cross-domain events. This is a
              project-level check, not built into the runner; we ran it during
              development.
            </p>
          </Section>

          <Section
            id="limitations"
            number="VI"
            title="Limitations"
            lead="A negative result, kept honest."
          >
            <blockquote className="pull-quote text-foreground">
              <p>
                This is a tool for hypothesis generation, not validation. In
                our own evidence gate over twenty-three candidate events,{' '}
                <span className="num text-accent">0 / 23</span> survived
                shift-control replication.
              </p>
            </blockquote>

            <p className="mt-8">What this tool is honest about:</p>
            <ul className="ml-6 list-disc space-y-2 text-base">
              <li>
                NMS is a similarity score, not a causal signal. Two correlated
                bursts can be coincidence, common-cause, or instrumentation
                artefact.
              </li>
              <li>
                Compression-based novelty conflates real anomalies with format
                changes, sampling artefacts, missing-data patterns, and clock
                errors.
              </li>
              <li>
                P-values are empirical and depend on{' '}
                <Code>null_shifts_count</Code>; tighter estimates need more
                shifts and more compute.
              </li>
              <li>
                The FDR target controls expected false discoveries across all
                edges, not individual events. A <em>significant event</em> is
                still a candidate until reproduced.
              </li>
            </ul>
            <p>
              Use the Results dashboard as a triage tool: find windows that are
              interesting enough to look at by hand — then go look at them by
              hand.
            </p>
          </Section>

          <Section
            id="api"
            number="VII"
            title="API reference"
            lead={
              <>
                The backend is a FastAPI service. Interactive Swagger / OpenAPI
                docs are served at <Code>/api/docs</Code> when the backend is
                running.
              </>
            }
          >
            <ul className="not-prose ml-0 list-none divide-y divide-border/60 border-y border-border/60">
              {[
                ['GET /api/health', 'Liveness probe.'],
                ['GET /api/sources', 'Catalogue of available data sources.'],
                ['POST /api/analyze', 'Submit a job. Returns 202 + job_id.'],
                ['GET /api/analysis/{id}', 'Fetch envelope + result if ready.'],
                ['GET /api/analysis/{id}/progress', 'SSE stream of progress updates.'],
              ].map(([path, body]) => (
                <li
                  key={path}
                  className={cn(
                    'grid grid-cols-12 gap-4 py-3 transition-colors hover:bg-foreground/[0.02]',
                  )}
                >
                  <Code>{path}</Code>
                  <span className="col-span-12 text-sm text-muted-foreground md:col-span-7 md:col-start-6">
                    {body}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-8">
              <Link
                to="/analyze?source=demo"
                className="inline-flex items-baseline gap-1 text-accent ink-underline"
              >
                Run a demo analysis <ArrowUpRight className="h-4 w-4" />
              </Link>{' '}
              to see the full envelope shape on the Results page.
            </p>
          </Section>
        </div>
      </div>
    </article>
  );
}
