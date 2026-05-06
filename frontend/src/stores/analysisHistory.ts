import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface HistoryEntry {
  jobId: string;
  label: string;
  startedAt: number;
  sourceIds: string[];
  status: 'pending' | 'running' | 'succeeded' | 'failed';
}

interface HistoryState {
  entries: HistoryEntry[];
  add: (entry: HistoryEntry) => void;
  update: (jobId: string, patch: Partial<HistoryEntry>) => void;
  remove: (jobId: string) => void;
  clear: () => void;
}

export const useAnalysisHistory = create<HistoryState>()(
  persist(
    (set) => ({
      entries: [],
      add: (entry) =>
        set((s) => ({
          entries: [entry, ...s.entries].slice(0, 25),
        })),
      update: (jobId, patch) =>
        set((s) => ({
          entries: s.entries.map((e) => (e.jobId === jobId ? { ...e, ...patch } : e)),
        })),
      remove: (jobId) =>
        set((s) => ({ entries: s.entries.filter((e) => e.jobId !== jobId) })),
      clear: () => set({ entries: [] }),
    }),
    { name: 'amsg.history.v1' },
  ),
);
