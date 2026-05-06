# Screenshots

Drop the five screenshots referenced from the root [`README.md`](../../README.md) here.

| File | Page | Capture |
|---|---|---|
| `hero.jpg` | Home (above the fold) | Just the visible viewport: title, abstract, CTA buttons, live status pill. Do **not** capture the full page. |
| `home.jpg` | Home (full page) | Full-page scroll: hero + Method steps + Figure (sample chart) + Limitations callout. |
| `analyze.jpg` | Analyze | Form with at least one source selected, date range visible, settings panel expanded. |
| `results.jpg` | Results | A completed `demo` run: hero metrics, Plotly time-series chart with event bands, NMS heatmap, p-value histogram, events table. |
| `docs.jpg` | Docs / Method | Method walkthrough with the marginalia table of contents visible on the right. |

## Capture settings

- **Theme:** dark (the default).
- **Viewport:** 1440 × 900 (or 1920 × 1080).
- **Format:** JPG or PNG. JPG is fine for screenshots if the file size stays
  reasonable; PNG gives crisper text.
- **Size:** keep each shot under ~500 KB. Compress with
  [`squoosh`](https://squoosh.app/) (MozJPEG ~75 quality, or oxipng for PNG).
- **Run:** use the bundled `demo` source so the data is reproducible offline.

## How to take the hero shot

`hero.jpg` is the only viewport-only shot. Three ways:

1. **Snipping Tool** (`Win + Shift + S`) — rectangle from header down to the
   CTA buttons.
2. **DevTools** — `F12` → `Ctrl + Shift + P` → `Capture screenshot` (without
   the word *full size*) → captures only the visible viewport.
3. **Crop `home.jpg`** — open it in any image editor and trim everything
   below the CTA row.

If you prefer a different filename extension, update the references in the
root `README.md` accordingly.
