import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatNumber(value: number, fractionDigits = 3): string {
  if (Number.isNaN(value) || !Number.isFinite(value)) return '—';
  if (Math.abs(value) >= 10_000) return value.toExponential(fractionDigits);
  return value.toFixed(fractionDigits);
}

export function formatPValue(p: number | null | undefined): string {
  if (p === null || p === undefined) return '—';
  if (p < 1e-4) return p.toExponential(2);
  return p.toFixed(4);
}

export function formatDuration(seconds: number): string {
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)} ms`;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds - m * 60);
  return `${m}m ${s}s`;
}
