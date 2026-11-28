# Page-wide figure detection

DocuRebuild proposes figure regions on a page so the user can review and crop
them. Proposals are local, deterministic and never become content on their own:
the user still confirms the crop, which creates a normal element. This document
describes the evidence sources, the ground-truth evaluation and the measured
results.

## Evidence sources

`backend/app/services/regions.py` (`propose_regions` -> `assemble_figures`)
combines four local signals:

| Signal | Source | Confidence | Notes |
| --- | --- | --- | --- |
| Embedded PDF raster image | `pdf.image_regions` | medium | Precise placement of an image XObject. |
| PDF vector artwork | `pdf.drawing_regions` | medium | Curves, diagonals and filled shapes; axis-aligned rules are ignored so table grids and page frames are not figures. |
| Raster ink cluster | `artwork.artwork_regions` | low | For photographed/scanned pages: ink the OCR text layout does not explain. |
| Caption band | `regions._figure_rects` | medium | The empty band above a `Figure`/`Fig`/`Diagram`/`Chart` caption. |

Assembly rules:

- An embedded image keeps its precise box; a caption band that describes the
  same area is merged onto it instead of offered twice.
- A vector drawing is dropped when an image or a detected table/equation already
  covers it (shading, backing, borders).
- Raster ink inside a detected table/equation is dropped.
- Proposals are clamped to the page, sorted by reading position, deduped at
  IoU >= 0.85, and suppressed when an existing element already covers them.
- Nothing is persisted or accepted automatically.

## Evaluation method

`backend/tests/figure_eval.py` scores proposals against hand-labelled boxes:
a proposal is a hit when its IoU with a truth box is at least 0.5, each box may
match at most once (greedy, highest IoU first), and precision/recall are the
usual definitions. `backend/tests/test_figure_eval.py` builds representative
pages, runs the real API pipeline, and prints the per-case table.

Ground truth is in PDF points for PDF cases (scaled to the rendered page) and in
image pixels for raster cases. Disposable projects and a mocked OCR engine are
used; no user data is touched.

## Results

Measured 28 November 2026 with the bundled PyMuPDF/Pillow stack, IoU >= 0.5:

| Case | Proposed | Truth | Precision | Recall |
| --- | --- | --- | --- | --- |
| pdf-image | 1 | 1 | 1.00 | 1.00 |
| pdf-vector-chart | 1 | 1 | 1.00 | 1.00 |
| pdf-captioned-image | 1 | 1 | 1.00 | 1.00 |
| pdf-shaded-backing | 1 | 1 | 1.00 | 1.00 |
| pdf-background | 0 | 0 | 1.00 | 1.00 |
| pdf-logo | 0 | 0 | 1.00 | 1.00 |
| pdf-multi-column | 1 | 1 | 1.00 | 1.00 |
| pdf-two-figures | 2 | 2 | 1.00 | 1.00 |
| raster-chart | 1 | 1 | 1.00 | 1.00 |
| raster-text-only | 0 | 0 | 1.00 | 1.00 |
| **Overall** | 8 | 8 | **1.00** | **1.00** |

TP=8, FP=0, FN=0, F1=1.00. This is a small, controlled corpus, not a claim of
general accuracy on arbitrary scanned books.

The evaluation caught one real defect, now fixed: a short caption under a wide
image produced two proposals (the precise image box and a narrower, shifted
caption band) because area-overlap alone fell below the merge threshold. The
band now merges when it shares most of the smaller box on both axes
(`regions._caption_band_matches`).

## Reproduction

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_figure_eval.py -q -s
```

## Limitations

- The caption-band heuristic still proposes the empty band above a figure caption
  even when no artwork is present. That is intentional (the band is the only
  signal on a caption-only page) but it can be a false positive; the user reviews
  and dismisses it.
- Raster ink detection is capped at 5 regions per page and runs on a 480 px
  grayscale copy, so very small or very large pages can miss weak figures.
- PDF image/drawing evidence is only used when the page is unrotated and has no
  geometry edits; otherwise those boxes would be in the wrong place.
- Region proposals require an OCR run. A PDF page with no OCR run returns
  `no_ocr_run` even though PDF artwork is deterministic.
- Opaque PDF figures with no readable vector paths and no embedded raster image
  are not proposed yet; that is the separate opaque-PDF task.
- The corpus is synthetic/controlled; real book pages with photographs, halftones
  and complex multi-figure layouts need a larger labelled set before quoting a
  general precision/recall figure.
