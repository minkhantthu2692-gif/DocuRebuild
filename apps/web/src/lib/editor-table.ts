/**
 * Manual table reconstruction settings.
 *
 * Tables are inserted empty and every value is typed by the user. This keeps the
 * manual path free of generated or guessed cell content, and bounds the table so
 * an accidental huge value cannot stall the editor.
 */
export const TABLE_MIN_SIZE = 1;
export const TABLE_MAX_SIZE = 10;

export function clampTableSize(value: number): number {
  if (!Number.isFinite(value)) return TABLE_MIN_SIZE;
  return Math.min(Math.max(Math.trunc(value), TABLE_MIN_SIZE), TABLE_MAX_SIZE);
}

export interface TableInsertOptions {
  rows: number;
  cols: number;
  withHeaderRow: boolean;
}

export function tableInsertOptions(
  rows: number,
  columns: number,
  withHeaderRow: boolean,
): TableInsertOptions {
  return {
    rows: clampTableSize(rows),
    cols: clampTableSize(columns),
    withHeaderRow,
  };
}
