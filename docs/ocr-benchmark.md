# Local OCR accuracy benchmark

This report records what the bundled OCR engine actually produces on known
text. It exists so that "accuracy first" is backed by numbers a person can
reproduce, not by an impression of how the editor looked.

## How it is measured

`backend/app/ocr_benchmark.py` scores the same Tesseract adapter the application
uses (same preprocessing, same engine detection, same language validation)
against a reference transcript. Two metrics are reported:

- **CER** - character error rate, the Levenshtein distance over characters
  divided by the reference length.
- **WER** - word error rate, the same over whitespace-separated words.

Text is normalised to NFC with collapsed whitespace before scoring. Case,
punctuation and Burmese combining marks stay significant, and no Zawgyi/Unicode
conversion is applied.

## Fixtures

`backend/tests/fixtures/ocr-synthetic` contains three A4 pages at 300 DPI:

| Case | Language data | Content |
| --- | --- | --- |
| `english-page` | `eng` | Ten lines of Latin prose about the product workflow |
| `burmese-page` | `mya` | Ten lines of Burmese prose about the product workflow |
| `mixed-page` | `eng+mya` | Six lines alternating Latin and Burmese |

The pages are rendered with Windows GDI+ text shaping
(`scripts/generate-ocr-fixtures.ps1`), so Burmese glyph clusters are shaped the
way a word processor renders them rather than being drawn as isolated code
points. The reference transcripts are the exact strings that were drawn.

These are synthetic pages, not scans: they have no skew, noise, bleed-through,
faded toner or photographic distortion. They measure the engine and the language
data, and they establish a regression baseline. They are **not** a claim about
accuracy on a real photographed book.

## Environment

| Item | Value |
| --- | --- |
| Machine | Intel N100, 4 cores, 16 GB RAM |
| OS | Windows 11 (10.0.26300) |
| Engine | Tesseract 5.4.0.20240606 (UB Mannheim build, bundled) |
| Language data | `eng` from the installer, `mya` from `tessdata_fast` |
| Page segmentation | Compared below: 3 (automatic) and 11 (sparse text) |

## How to reproduce

From the repository root, with the bundled runtime:

```powershell
$env:DOCUREBUILD_TESSERACT_CMD = "dist\desktop\tesseract\tesseract.exe"
$env:DOCUREBUILD_TESSDATA_DIR = "dist\desktop\tesseract\tessdata"
Set-Location backend
.venv\Scripts\python.exe -m app.ocr_benchmark tests/fixtures/ocr-synthetic
.venv\Scripts\python.exe -m app.ocr_benchmark tests/fixtures/ocr-synthetic --segmentation-mode 11
```

## Results - automatic page segmentation (Tesseract default, mode 3)

| Case | CER | WER | Confidence | Reference characters |
| --- | --- | --- | --- | --- |
| `english-page` | 0.14% | 0.93% | 95.8 | 702 |
| `burmese-page` | 85.60% | 353.33% | 43.4 | 486 |
| `mixed-page` | 40.27% | 142.11% | 75.5 | 226 |
| **Overall** | **35.93%** | **85.35%** | | 1414 |

Automatic layout analysis fails on the Burmese page: it merges rows, then reads
the merged band as noise. This is a segmentation failure, not a traineddata
failure - the engine recognises the same characters well when the lines stay
separate.

## Results - sparse text segmentation (mode 11)

| Case | CER | WER | Confidence | Reference characters |
| --- | --- | --- | --- | --- |
| `english-page` | 0.28% | 1.85% | 95.8 | 702 |
| `burmese-page` | 5.56% | 53.33% | 75.6 | 486 |
| `mixed-page` | 0.88% | 10.53% | 89.5 | 226 |
| **Overall** | **2.19%** | **12.74%** | | 1414 |

The remaining Burmese character errors are mostly the sentence terminator `။`
read as `1`, plus a few vowel-sign confusions. WER is high because Burmese does
not separate words with spaces; the metric therefore counts line-level
substitutions rather than word-level ones. CER is the meaningful figure for
this script.

## Application behaviour

- The OCR dialog exposes the page layout as a user-visible choice: Automatic,
  Single column, Single block, Sparse text. The run request carries
  `page_segmentation_mode`, and an unsupported value is rejected with
  `ocr_invalid_segmentation_mode` instead of being silently replaced.
- Choosing a language combination that includes `mya` preselects Sparse text
  until the user picks a layout themselves.
- The backend default stays mode 3 and can be changed with
  `DOCUREBUILD_OCR_PAGE_SEGMENTATION_MODE` for installations that only process
  one script.
- Every run records its languages and the segmentation mode in the project
  activity log.

## Limitations

- Three synthetic pages are a baseline, not a corpus. A redacted set of real
  English and Burmese scans is still the right next step, and the harness
  already accepts stored transcripts for scoring without an engine installed.
- The benchmark scores whole-page text extraction. It does not score table cell
  grouping, figure captions, equation recognition or PDF text-layer extraction.
- The `mya` model ships with `tessdata_fast`. `tessdata_best` was not bundled
  because it is several times larger and slower; it may improve character
  accuracy and can be dropped into `tessdata` by a user who prefers it.
- Zawgyi-encoded text is out of scope: no conversion is applied, and the
  benchmark measures exactly what the engine produced.
