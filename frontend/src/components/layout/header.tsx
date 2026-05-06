import { Github } from 'lucide-react';
import { NavLink } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

import { ThemeToggle } from './theme-toggle';

const NAV = [
  { to: '/', label: 'Index', end: true },
  { to: '/analyze', label: 'Analyze' },
  { to: '/results', label: 'Results' },
  { to: '/docs', label: 'Method' },
];

export function Header() {
  return (
    <header className="sticky top-0 z-30 w-full border-b border-border/60 bg-background/85 backdrop-blur">
      <div className="container flex h-14 items-center justify-between gap-6">
        {/* Wordmark — set in serif display, deliberately literary. */}
        <NavLink to="/" className="group flex items-baseline gap-3">
          <span className="display text-xl leading-none">amsg</span>
          <span className="marginalia hidden text-[0.625rem] sm:inline">
            Anomaly Pipeline · v0.1
          </span>
        </NavLink>

        <nav
          aria-label="Primary"
          className="hidden items-center gap-7 md:flex"
        >
          {NAV.map(({ to, label, end }, i) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'group relative inline-flex items-baseline gap-2 text-sm transition-colors',
                  isActive
                    ? 'text-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )
              }
            >
              {({ isActive }) => (
                <>
                  <span className="num text-[10px] text-muted-foreground/70">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span className={cn('relative', isActive && 'ink-underline')}>
                    {label}
                  </span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-1">
          <Button asChild variant="ghost" size="icon" aria-label="GitHub repository">
            <a
              href="https://github.com/"
              target="_blank"
              rel="noreferrer noopener"
            >
              <Github />
            </a>
          </Button>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
