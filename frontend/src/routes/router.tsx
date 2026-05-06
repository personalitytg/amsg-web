import { createBrowserRouter } from 'react-router-dom';

import { AppShell } from '@/components/layout/app-shell';
import { AnalyzePage } from '@/features/analyze/AnalyzePage';
import { DocsPage } from '@/features/docs/DocsPage';
import { HomePage } from '@/features/home/HomePage';
import { ResultsPage } from '@/features/results/ResultsPage';

import { NotFoundPage } from './NotFoundPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'analyze', element: <AnalyzePage /> },
      { path: 'results', element: <ResultsPage /> },
      { path: 'results/:id', element: <ResultsPage /> },
      { path: 'docs', element: <DocsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);
