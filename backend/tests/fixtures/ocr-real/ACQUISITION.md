# Real-Scan OCR Corpus

`ocr-synthetic` proves the pipeline works on pages this project rendered itself.
It cannot say how the engine behaves on paper: scanner skew, show-through, foxing,
letterpress type, dot leaders and tables all disappear when text is drawn with
GDI+. This folder holds a small corpus of genuine, public-domain scans with
reference transcripts typed from the page, so an accuracy claim can be backed by
real material.

The corpus is deliberately small. It is evidence, not a training set, and every
page was chosen because it exercises a documented weakness: prose, a dense
statistical table, and a three-column English/Burmese/transliteration page.

Nothing here is private, in copyright, or personally identifying. All four pages
come from published books that are in the public domain, and none of them contains
handwriting, names, addresses or other personal data.

## Provenance

| Case | Source | Page | Licence |
| --- | --- | --- | --- |
| `english-prose` | [The novels of Jane Austen, vol. 3: Pride and Prejudice](https://archive.org/details/novelsjaneauste05unkngoog) (Edinburgh: Grant, 1905) | scan `n60`, printed page 48 | Public domain; Internet Archive records `NOT_IN_COPYRIGHT` |
| `english-table` | [Statistical Abstract of the United States 1975, section 1-34](https://archive.org/details/sim_statistical-abstract-of-the-united-states_1975_section-1-34) (US Government) | scan `n24`, table "No. 1. Population and Area: 1790 to 1970" | Public domain (US Government work) |
| `burmese-mixed` | [Elementary hand-book of the Burmese language](https://archive.org/details/cu31924022058931) (Rangoon: Government Printing, Burma, 1898) | scan `n30`, printed page 15 | Public domain; published 1898, Cornell University Library scan |
| *blocked* | [Prayer book in Burmese](https://archive.org/details/PrayerBookInBurmese) (Bassein: Catholic Mission Press, 1868) | scan `n8`, printed page iv | Public domain mark 1.0 |

Files as committed (SHA-256, bytes):

```text
214fd28364446f46580bd11b6666fb4e0c0edec5bafb25e6924a689c433495b3   357022  english/pride-prejudice-1905-p48.jpg
412ad9e3184d7e36d693d8ccd1ddff8339344816e0469d95f94af5c59985f270  2103977  table/statistical-abstract-1975-table1.png
6ce59e54c9f9d4958a95ee1cc10b6f8b1ac7c425df493d1c31b543c52023c7f4   376492  mixed/burmese-handbook-1898-p15.jpg
3b43897dd6665a24c00fcbafecd5406948c716185fde218132eb1de169129ef8   260876  blocked/prayer-book-1868-piv.jpg
```

### Exact downloads

```text
english/pride-prejudice-1905-p48.jpg
  https://archive.org/download/novelsjaneauste05unkngoog/page/n60_w1200.jpg
  1634 x 2396 source, cropped to the top 2080 rows (see below)

table/statistical-abstract-1975-table1.png
  https://iiif.archive.org/iiif/sim_statistical-abstract-of-the-united-states_1975_section-1-34$24/full/2264,/0/default.jpg
  2264 x 3384 source, cropped to the table area (see below)

mixed/burmese-handbook-1898-p15.jpg
  https://archive.org/download/cu31924022058931/page/n30_w1200.jpg
  1838 x 2781, used uncropped

blocked/prayer-book-1868-piv.jpg
  https://iiif.archive.org/iiif/PrayerBookInBurmese$8/full/1280,/0/default.jpg
  1280 x 1916, used uncropped
```

## Preparation

Only two edits were made, and both are recorded here so a reader can re-derive
the committed file from the download:

1. **English page — watermark strip removed.** The Internet Archive copy carries a
   "Digitized by Google" strip across the bottom margin. It is a scanning artefact,
   not page content, so the image was cropped to rows `0..2080` of 2396. Nothing
   printed on the page was removed; the page number 48 is above the cut.
2. **Table — page region cropped.** The source is a full journal page. The image was
   cropped to the box `(left, upper, right, lower) = (181, 304, 2173, 1810)` of the
   2264 x 3384 scan, giving 1992 x 1506 — approximately `x = 8.0%..96.0%`,
   `y = 9.0%..53.5%`. It contains the table title, column headings, all 21 data
   rows, the footnotes and the source line, and nothing else.

Both crops were re-derived from fresh downloads while this document was written.
The table crop matches the committed PNG pixel for pixel; the English crop matches
the fresh download apart from JPEG re-encoding noise.

No deskew, denoise, binarisation, resampling or contrast change was applied. The
images are the scan as delivered, so the benchmark measures the engine against
paper rather than against a pre-cleaned ideal.

**Resolution.** None of the images carries DPI metadata. At their printed page
sizes the scans are a few hundred dpi equivalents, but that is an estimate from
the pixel dimensions, not a measured value. The OCR adapter re-encodes every image
to PNG without a resolution hint before calling Tesseract, so the engine never sees
a DPI value on this code path. That is a limitation of the measurement, not of the
scan: a run is reproducible with this application build, and the pixel dimensions
above are the honest description of the input.

## Ground truth

Each `.txt` file was typed from the scan, never copied from OCR output. Conventions,
applied uniformly:

- **Dot and dash leaders are omitted.** Runs of `. . .` and `-----` that fill a
  column gap are typography, not text. The rule is applied to both the handbook's
  `...` separators and the table's date leaders. Anything the engine emits for them
  therefore counts as an insertion.
- **End-of-line hyphenation is resolved.** The English page prints `de-` at the end
  of a line and `spatched` at the start of the next; the reference reads
  `despatched`. The engine's output keeps the break, which is scored as a real word
  error because the application does not join hyphenated words either.
- **Printed spacing is kept.** The English page sets `absent :` with a space before
  the colon; the reference keeps it.
- **Superscript footnote markers are written as plain digits** (`2 39,818,449`,
  `1 Excludes Alaska and Hawaii.`), because that is what the page says and what a
  text reconstruction is expected to produce.
- **Tables are transcribed row by row**, each row on one line with cells separated
  by spaces, in left-to-right column order. That is the reading order a table
  reconstruction is expected to produce.
- **Burmese is stored in Unicode logical order**, never Zawgyi and never converted.
  `normalize_text` applies NFC, and no Zawgyi/Unicode conversion happens anywhere.

### Verification performed

- **Table:** every row was checked arithmetically before it was accepted. Gross
  area minus land area equals the water column in all 21 rows, each population
  increase equals the difference between consecutive census counts (the 1950
  national row is measured against the 1940 count including Alaska and Hawaii,
  which the table does not print as a separate row), and the percentage column is
  consistent with those differences. A misread digit breaks one of those
  identities, so the numbers are corroborated by the page's own internal logic.
- **Handbook:** every Burmese entry was read from the scan and then cross-checked
  against the transliteration the book prints beside it. The transliteration is an
  independent key on the same page: `Ywet-thî` for ရွက်သည်, `pwẹ-thî` for ပွေ့သည်,
  `Sa-gâ:pyaw:thî` for စကားပြောသည်. It also resolved two glyphs that are ambiguous in
  this typeface, where the wa medial ွ and the ra medial ြ are easy to confuse.

### Known limitations of the reference

- **One transcriber, no second proofreader.** These transcripts were produced for
  this benchmark and have not been checked by a second person. They are better than
  no reference, but they are not a scholarly edition.
- **Burmese tone marks are the least certain part.** `့` (creaky) and `း` (heavy)
  are a few pixels apart at this size, and a handful of marks were inferred from
  the printed transliteration rather than read with certainty. The affected
  characters are a small share of the ~280 Burmese characters on the page, so the
  mixed-page CER carries roughly one percentage point of reference noise.
- **The English and table references are not affected by this.** They are plain
  Latin text at large size and were read without ambiguity.

If a native Burmese reader ever re-checks `mixed/burmese-handbook-1898-p15.txt`, the
numbers in `docs/ocr-benchmark.md` should be regenerated.

## Blocked: a Burmese-only page

The corpus has no scored Burmese-only case, and that is a deliberate, documented
gap rather than an oversight.

The 1868 *Prayer book in Burmese* page in `blocked/` is a genuine, legible, public
domain Burmese page, and the engine's behaviour on it is recorded there
(`probe.json`, plus the raw output at page segmentation modes 3 and 11). It is not
scored because **no trustworthy reference exists for it**:

- There is no proofread digital text of this edition. Burmese Wikisource has no
  proofread `Page:` transcription for it, and the Internet Archive's `djvu.txt`
  derivative for the item is unusable (no page breaks, heavy corruption).
- The page is hand-set 1868 Burmese type with archaic spelling. Transcribing it by
  eye, once, with no independent check, would produce a reference whose own error
  rate is unknown - and a CER measured against an unverified reference is not
  evidence.
- Every other Burmese source examined either ships OCR-generated "ground truth"
  (which would mean measuring Tesseract against another OCR engine) or is
  research-licensed and not redistributable.

What would unblock it: a page whose Burmese text can be independently verified -
for example a modern official publication with a known Unicode text, or the same
page transcribed and checked by two Burmese readers. The fixture and the recorded
engine output are kept so that work only has to produce the transcript.

## Reproducing

From the repository root, with the bundled Tesseract:

```powershell
$env:DOCUREBUILD_TESSERACT_CMD = "$PWD\dist\desktop\tesseract\tesseract.exe"
$env:DOCUREBUILD_TESSDATA_DIR = "$PWD\dist\desktop\tesseract\tessdata"
cd backend
.\.venv\Scripts\python.exe -m app.ocr_benchmark tests/fixtures/ocr-real
.\.venv\Scripts\python.exe -m app.ocr_benchmark tests/fixtures/ocr-real --segmentation-mode 11 --json
```

Results and their interpretation live in `docs/ocr-benchmark.md`.
