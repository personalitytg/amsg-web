import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';

export function NotFoundPage() {
  return (
    <section className="container flex min-h-[60vh] flex-col items-center justify-center text-center">
      <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">404</p>
      <h1 className="mt-4 text-3xl font-bold">Page not found</h1>
      <p className="mt-2 max-w-sm text-muted-foreground">
        The route you tried does not exist in this app.
      </p>
      <Button asChild variant="outline" className="mt-8">
        <Link to="/">Back home</Link>
      </Button>
    </section>
  );
}
