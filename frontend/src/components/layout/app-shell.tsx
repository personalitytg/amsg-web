import { Outlet } from 'react-router-dom';

import { Footer } from './footer';
import { Header } from './header';

export function AppShell() {
  return (
    <div className="relative flex min-h-screen flex-col">
      {/* Vignette + grain are handled in body via index.css.
          One additional plate: a faint top hairline that runs across the
          whole document — like the printed plate edge of a page. */}
      <div
        aria-hidden
        className="pointer-events-none fixed left-0 right-0 top-0 z-40 h-px bg-border/70"
      />

      <Header />
      <main className="flex-1">
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}
