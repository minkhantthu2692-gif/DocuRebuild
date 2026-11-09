/**
 * Client-side pre-validation for page imports.
 *
 * The backend remains the source of truth (it checks real file contents), but
 * catching obvious problems here avoids uploading files that cannot succeed.
 */

export const ACCEPTED_IMAGE_EXTENSIONS = [
  ".jpg",
  ".jpeg",
  ".png",
  ".webp",
  ".bmp",
  ".tif",
  ".tiff",
] as const;

export const PDF_EXTENSION = ".pdf";

export const ACCEPTED_IMPORT_EXTENSIONS = [
  ...ACCEPTED_IMAGE_EXTENSIONS,
  PDF_EXTENSION,
] as const;

export const IMAGE_ACCEPT_ATTRIBUTE = ACCEPTED_IMAGE_EXTENSIONS.join(",");
export const IMPORT_ACCEPT_ATTRIBUTE = ACCEPTED_IMPORT_EXTENSIONS.join(",");

export type RejectionReason = "unsupported" | "too_large";

export interface RejectedImportFile {
  file: File;
  reason: RejectionReason;
}

export interface ImportFileSelection {
  accepted: File[];
  rejected: RejectedImportFile[];
}

function extensionOf(name: string): string {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index).toLowerCase() : "";
}

export function isPdfFile(file: File): boolean {
  return extensionOf(file.name) === PDF_EXTENSION;
}

export function isSupportedImageFile(file: File): boolean {
  return (ACCEPTED_IMAGE_EXTENSIONS as readonly string[]).includes(extensionOf(file.name));
}

export function isSupportedImportFile(file: File, allowPdf: boolean): boolean {
  if (isSupportedImageFile(file)) return true;
  return allowPdf && isPdfFile(file);
}

export function partitionImportFiles(
  files: Iterable<File>,
  maxBytes: number | null,
  allowPdf = false,
): ImportFileSelection {
  const accepted: File[] = [];
  const rejected: RejectedImportFile[] = [];

  for (const file of files) {
    if (!isSupportedImportFile(file, allowPdf)) {
      rejected.push({ file, reason: "unsupported" });
      continue;
    }
    if (maxBytes !== null && file.size > maxBytes) {
      rejected.push({ file, reason: "too_large" });
      continue;
    }
    accepted.push(file);
  }

  return { accepted, rejected };
}
