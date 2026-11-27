# Real File Practical Check - 2026-11-27

Tested commit: `8cb208c` (the repository is currently on `main` at that commit).

## Files tested

- `MET-51051 for exam.pdf`: 8 pages
- 5 attached JPG files:
  - `photo_2026-11-27_17-47-53.jpg`
  - `photo_2026-11-27_17-47-47.jpg`
  - `photo_2026-11-27_17-34-14.jpg`
  - `photo_2026-11-27_17-34-00.jpg`
  - `photo_2026-11-27_17-33-43.jpg`

The normal application import workflow created a test project and imported all 13
pages: 8 PDF pages and 5 image pages.

## Findings

- Page rendering worked for the PDF and image imports. Source thumbnails and the
  full source view showed the supplied pages correctly.
- Embedded PDF text on PDF page 1 was reasonably accurate and preserved the page
  headings, paragraphs, figure caption, and page number. It was presented as an
  editable OCR proposal and did not claim OCR confidence.
- The printed schedule image (page 10) rendered with usable Burmese text. Burmese
  OCR with sparse-text layout produced 49 text blocks and an average reported
  confidence of 71%. Most headings and longer Burmese labels were recognizable,
  but dates, numbers, and several low-confidence words contained OCR errors.
- The mixed English/Burmese open-book image (page 11) rendered, and English OCR
  ran successfully. It reported 56% average confidence; the handwritten margin
  notes and mixed scripts were not reliably recognized, so manual review is
  necessary.
- OCR results retained the unverified/source-note treatment and could be inserted
  into the editor.
- Editing, autosave, and reopen persistence were verified with a practical review
  note appended to the inserted schedule OCR text. The note remained in the
  document after a browser reload.
- The plain-text export API returned HTTP 200 and a 2,106-byte
  `Real-File-Practical-Check.txt` attachment containing the edited Burmese text
  and source note.

## Major layout and reading-order observations

- PDF text page 1 kept paragraph and heading structure recognizable.
- The schedule table was fragmented into individual OCR blocks rather than
  reconstructed as a single table. Reading order was mostly understandable, but
  dates and table rows require manual correction.
- Mixed English/Burmese handwriting and overlaid annotations produced poor or
  fragmented recognition. The source image remains more reliable than OCR for
  those areas.
- The PDF and images were not modified.

## Fixes

- No application code changes were needed for these files. The imported pages,
  OCR proposals, editing, persistence, and export output all worked without a
  reproducible application defect that could be corrected safely within this
  lightweight check.

## Remaining issues / unverified items

- OCR accuracy for handwritten annotations, mixed-script scans, dates, and dense
  table numbers should remain treated as manual-review work.
- The browser automation download event did not fire for the in-app plain-text
  export action. The server-side export itself was verified directly and returned
  HTTP 200. A desktop-build end-to-end browser download check remains pending.
- The initial project route returned the dashboard immediately after creation in
  development mode; direct navigation to the project route opened the workspace
  correctly. This was not changed because it was not reproducible enough to
  isolate from the development navigation/test setup.
