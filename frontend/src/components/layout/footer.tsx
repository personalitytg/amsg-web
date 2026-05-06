export function Footer() {
  return (
    <footer className="mt-24 border-t border-border/60">
      <div className="container grid grid-cols-1 gap-10 py-12 md:grid-cols-12">
        {/* Colophon — like the back-of-book typesetter's note. */}
        <div className="md:col-span-6">
          <div className="marginalia mb-3">Colophon</div>
          <p className="reading max-w-md text-base">
            Set in <span className="italic">Fraunces</span> for display and
            <span className="italic"> Albert Sans</span> for body, with{' '}
            <span className="italic">IBM Plex Mono</span> handling all numerals.
            Compression-based cross-domain anomaly detection over geophysical
            time series — a normalized variant of{' '}
            <abbr title="Normalized Compression Distance" className="no-underline">
              NCD
            </abbr>{' '}
            (Cilibrasi &amp; Vitányi, 2005).
          </p>
        </div>

        <div className="md:col-span-3">
          <div className="marginalia mb-3">Index</div>
          <ul className="space-y-1.5 text-sm">
            <li>
              <a className="hover:text-accent" href="/">
                Front matter
              </a>
            </li>
            <li>
              <a className="hover:text-accent" href="/analyze">
                Analyze
              </a>
            </li>
            <li>
              <a className="hover:text-accent" href="/results">
                Results
              </a>
            </li>
            <li>
              <a className="hover:text-accent" href="/docs">
                Method
              </a>
            </li>
          </ul>
        </div>

        <div className="md:col-span-3">
          <div className="marginalia mb-3">Apparatus</div>
          <ul className="space-y-1.5 text-sm">
            <li>
              <a
                className="hover:text-accent"
                href="https://github.com/"
                target="_blank"
                rel="noreferrer noopener"
              >
                Source repository
              </a>
            </li>
            <li>
              <a className="hover:text-accent" href="/api/docs">
                API reference
              </a>
            </li>
            <li>
              <a className="hover:text-accent" href="/docs#limitations">
                Limitations
              </a>
            </li>
          </ul>
        </div>
      </div>

      <div className="border-t border-border/60">
        <div className="container flex items-center justify-between py-4 text-xs">
          <span className="marginalia">© MMXXVI · MIT</span>
          <span className="marginalia">
            Pressed in dark warm bistre · No.{' '}
            <span className="num">001</span>
          </span>
        </div>
      </div>
    </footer>
  );
}
