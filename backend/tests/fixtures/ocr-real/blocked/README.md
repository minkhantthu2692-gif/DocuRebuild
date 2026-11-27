# Blocked case: Burmese-only page without a trustworthy reference

This folder is **not** part of the benchmark manifest. `manifest.json` does not
reference it and `python -m app.ocr_benchmark tests/fixtures/ocr-real` does not
score it.

It is kept because the page is real evidence of how the local engine behaves on
hand-set Burmese type, and because reproducing that observation should not require
finding the page again.

| File | What it is |
| --- | --- |
| `prayer-book-1868-piv.jpg` | Page iv of *Prayer book in Burmese* (Bassein: Catholic Mission Press, 1868), 1280 x 1916, public domain mark 1.0 |
| `probe.json` | Engine version, mean confidence and output size for both runs |
| `prayer-book-1868-piv.psm3.txt` | Raw Tesseract output, automatic page segmentation |
| `prayer-book-1868-piv.psm11.txt` | Raw Tesseract output, sparse-text page segmentation |

## Why there is no CER for it

A Character Error Rate is only evidence if the reference is known to be right.
For this page it is not:

- No proofread transcription of this edition exists. Burmese Wikisource has no
  proofread `Page:` text for it, and the Internet Archive `djvu.txt` derivative is
  unusable: it has no page breaks and the Burmese is corrupted.
- The type is 1868 hand-set Burmese with archaic spelling. A single pass typed by
  eye, with no independent check, would have an unknown error rate of its own.
- Sources that do ship "ground truth" for Burmese scans (for example
  `alexbeatson/burmese_ocr_data`) generated it with another OCR engine, so scoring
  against it would compare two engines rather than measure accuracy.

The recorded runs are therefore reported as an observation, not as an accuracy
figure. See `docs/ocr-benchmark.md` for the numbers and how they should be read.

## What would unblock it

Either:

1. a page whose Burmese text can be verified independently - a modern official
   publication with a known Unicode text, or a scan of a text that already has a
   proofread transcription; or
2. this page transcribed and checked by two Burmese readers, with disagreements
   resolved against the scan.

In case 2, add a `reference` and move the case into `manifest.json`; nothing else
needs to change.
