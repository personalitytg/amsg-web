# AMSG Web — Frontend

React 18 + TypeScript + Vite single-page app for the AMSG anomaly pipeline.

## Layout

```
src/
  main.tsx                Entrypoint, mounts <App />
  App.tsx                 ThemeProvider + QueryClient + Router + Toaster
  index.css               Tailwind base, design tokens, dark/light variables

  routes/
    router.tsx            createBrowserRouter with AppShell
    NotFoundPage.tsx

  components/
    layout/               app-shell, header, footer, theme-provider, theme-toggle
    ui/                   button, card, input, label, badge, skeleton, toaster

  features/               Feature-first folders, each owns its UI + hooks
    home/HomePage.tsx
    analyze/AnalyzePage.tsx
    results/ResultsPage.tsx
    docs/DocsPage.tsx

  lib/
    api.ts                Typed axios client + SSE subscriber
    types.ts              Wire types mirroring backend Pydantic schemas
    queryClient.ts        TanStack Query default config
    utils.ts              cn(), number/p-value formatters

  stores/
    analysisHistory.ts    Zustand persisted store of past job ids
```

## Run locally

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api → :8000
```

By default Vite proxies `/api` to `http://localhost:8000`. Override with
`VITE_API_TARGET` (proxy target during dev) or `VITE_API_BASE_URL` (the URL the
client actually fetches from in production).

## Scripts

| Script | Purpose |
|---|---|
| `npm run dev` | Vite dev server with HMR |
| `npm run build` | Type-check then build to `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run lint` | ESLint (zero-warning policy) |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run format` / `format:check` | Prettier |

## Tech choices

- **Vite + React 18 + TS** — fastest local DX, strict types end-to-end.
- **Tailwind + shadcn-style primitives** — design-system tokens via CSS
  variables, dark mode through a `class` toggle on `<html>`.
- **Recharts** for everyday charts, **Plotly** for the time-series with
  zoom/pan and synchronized hover.
- **TanStack Query** for server state, **Zustand** for tiny client state
  (theme, history). React Context only for theme.
- **Framer Motion** for page-level transitions and hero entrances.
- **sonner** for toasts.

## Design tokens

Colour, radius and shadow tokens live in `src/index.css` under `:root` and
`.dark`. To re-skin, edit those CSS variables — Tailwind reads them via
`hsl(var(--token))`.

## Status

- Step 2 (skeleton) is in. Routing, layout, theme, API client, types, stores,
  primitives — all present.
- Step 3 (page content) is next: full Analyze form with date-range picker
  + multi-select, Results with charts/heatmap/table, Home landing, Docs.
