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

## Synthetic fixtures

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
.venv\Scripts\python.exe -m app.ocr_benchmark tests/fixtures/ocr-real
.venv\Scripts\python.exe -m app.ocr_benchmark tests/fixtures/ocr-real --segmentation-mode 11 --json
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

## Real-scan corpus

`backend/tests/fixtures/ocr-real` holds three public-domain page scans with
transcripts typed from the page. Provenance, SHA-256, preparation steps and the
transcription conventions are in
`backend/tests/fixtures/ocr-real/ACQUISITION.md`.

| Case | Category | Languages | Content |
| --- | --- | --- | --- |
| `english-prose` | `english` | `eng` | 1905 letterpress novel page: running head, page number, one end-of-line hyphen |
| `english-table` | `table` | `eng` | 1975 US statistical table: 21 data rows, 8 columns, rules, leaders, footnotes |
| `burmese-mixed` | `mixed` | `eng+mya` | 1898 English/Burmese/transliteration glossary page, three columns, 30 entries |

A fourth page - an 1868 Burmese prayer book - is kept in
`backend/tests/fixtures/ocr-real/blocked/` but is **not scored**, because no
trustworthy reference for it exists. See "The Burmese-only gap" below.

None of the images carries resolution metadata, and the adapter re-encodes to PNG
without one before calling Tesseract, so the engine receives no DPI hint on this
path. The pixel dimensions and the exact download URLs are the honest description
of the input.

### Results - real scans, automatic page segmentation (mode 3)

| Case | CER | WER | Confidence | Reference characters |
| --- | --- | --- | --- | --- |
| `english-prose` | 0.47% | 3.64% | 96.1 | 637 |
| `english-table` | 50.78% | 96.40% | 86.7 | 2617 |
| `burmese-mixed` | 45.33% | 97.78% | 70.5 | 1039 |
| **Overall** | **42.00%** | **80.60%** | | 4293 |

### Results - real scans, sparse text (mode 11)

| Case | CER | WER | Confidence | Reference characters |
| --- | --- | --- | --- | --- |
| `english-prose` | 0.47% | 3.64% | 96.0 | 637 |
| `english-table` | 22.43% | 92.54% | 85.6 | 2617 |
| `burmese-mixed` | 36.77% | 76.30% | 74.1 | 1039 |
| **Overall** | **22.64%** | **73.66%** | | 4293 |

### What each number means

**Clean English prose is not a problem.** Three character edits in 637: the
printer's space in `absent :` is dropped, and the line-break hyphen in
`de-spatched` is kept, so `despatched` becomes two words. Capitalisation,
punctuation and the page number are exact. A 1905 letterpress page at this
resolution is effectively solved by the bundled engine.

**A printed table is not solved, even though the engine is confident.** Mean
confidence is 86.7 and most digits are right, but the reconstructed text is
unusable as a table:

- numbers are split at the thousands separator (`3,929,214` becomes
  `3, 929, 214`), so every numeric cell costs three tokens;
- column rules come back as `|` and row leaders as `---` or `...`;
- the stacked header block (`RESIDENT POPULATION`, `Per square mile of land
  area`, `Increase over preceding census`) is read out of order and partly
  merged;
- stray marks on the rules become invented tokens (`ee ee NE EEE`).

Sparse text halves CER (50.78% to 22.43%) because it keeps each printed line
together, which is the reading order a table needs. WER barely moves (96.40% to
92.54%) because the separator splitting survives either way. This is a
**reconstruction** gap rather than a recognition gap: the table path needs
geometry, and the adapter already stores the word boxes that would supply it.
Acting on that is separate work, not part of this measurement.

**Mixed English/Burmese is poor, and the Burmese column is the reason.** 36.77%
CER at mode 11. Representative failures, taken from both modes:

| Reference | Engine |
| --- | --- |
| ရေကူးသည် | ရေထူးသည် |
| ထွက်သည် | တွက်သည် |
| ပွေ့သည် | ဌေသည် |
| စီးသည် | ပးသည် (mode 3), dropped (mode 11) |
| `Ywet-thî` | `Ywet-thi` |
| `’Tan:thî` | `Tamsthi` |

The dot leaders are read as text (`vee`, `we`, `. . .`), the transliteration's
circumflex and dot-below marks are dropped, the Ride line loses its Burmese and
transliteration at mode 11, and entries are read out of order. The English words
on the same page are correct, so the failure is specific to the Burmese column
and to the leaders between columns.

### The Burmese-only gap

The corpus has no scored Burmese-only case. The 1868 prayer book page in
`backend/tests/fixtures/ocr-real/blocked/` is real evidence - mean confidence
35.5 at mode 3 and 32.2 at mode 11, output unusable at both - but it is reported
as an observation, not as a CER, because no trustworthy transcript of that
edition exists and a single unchecked pass typed by eye would not be a reference.
`blocked/README.md` records what would unblock it.

So the corpus does **not** yet answer "how accurate is Burmese on a real page"
with a single number. It answers it in the mixed case, where the Burmese column
is visibly mangled while the Latin columns are clean, and it records the
Burmese-only failure without inventing a reference for it.

### Synthetic versus real

The synthetic Burmese page scores 5.56% CER at mode 11; the real mixed page
scores 36.77% at the same setting. The two are not like-for-like - different
pages, different language mixes - but the direction is unambiguous, and it is
the direction the earlier reports predicted. The synthetic figure measures the
engine and the language data. It does not describe paper. Whenever a claim is
about scanned books, quote the real-scan table above, not the synthetic one.

## Practical supplied-file check

On 27 November 2026, a separate lightweight workflow check imported 8 pages
from `MET-51051 for exam.pdf` and 5 supplied JPG scans without changing the
source files. This was a usability check, not a CER/WER benchmark:

- the PDF page 1 embedded text was recognizable and editable;
- a Burmese schedule image retained recognizable table structure at 71%
  reported OCR confidence, but dates, numbers and low-confidence words needed
  manual review;
- a mixed English/Burmese photographed page ran OCR at 56% average confidence,
  but handwriting and overlaid annotations fragmented the result;
- inserted OCR text could be edited, autosaved, reopened and exported as plain
  text.

These observations do not change the measured corpus results above and should
not be treated as a population estimate or a replacement for the reference
transcripts.

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

- The real-scan corpus is three pages from three books, transcribed by one
  person and not checked by a second proofreader. It is evidence about this
  adapter on this material, not a population estimate for scanned books in
  general. Burmese tone marks are the least certain part of the mixed reference.
- There is no scored Burmese-only case. The one suitable page that was found has
  no trustworthy reference, so its engine output is recorded in
  `backend/tests/fixtures/ocr-real/blocked/` as an observation, not as a CER.
- None of the images carries DPI metadata, and the adapter re-encodes to PNG
  without a resolution hint, so a run cannot be restated as "X% at N dpi". The
  pixel dimensions and exact source URLs are recorded instead.
- The synthetic pages remain the regression baseline for the pipeline; the real
  pages are the honest accuracy reference. Quote the real-scan table whenever the
  claim is about scanned paper.
- Both corpora score whole-page text extraction. They do not score table cell
  grouping, figure captions, equation recognition or PDF text-layer extraction.
- The `mya` model ships with `tessdata_fast`. `tessdata_best` was not bundled
  because it is several times larger and slower; it may improve character
  accuracy and can be dropped into `tessdata` by a user who prefers it.
- Zawgyi-encoded text is out of scope: no conversion is applied, and the
  benchmark measures exactly what the engine produced.
