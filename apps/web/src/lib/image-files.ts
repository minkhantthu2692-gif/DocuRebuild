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

export const IMAGE_ACCEPT_ATTRIBUTE = ACCEPTED_IMAGE_EXTENSIONS.join(",");

export type RejectionReason = "unsupported" | "too_large";

export interface RejectedImageFile {
  file: File;
  reason: RejectionReason;
}

export interface ImageFileSelection {
  accepted: File[];
  rejected: RejectedImageFile[];
}

function extensionOf(name: string): string {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index).toLowerCase() : "";
}

export function isSupportedImageFile(file: File): boolean {
  return (ACCEPTED_IMAGE_EXTENSIONS as readonly string[]).includes(extensionOf(file.name));
}

export function partitionImageFiles(
  files: Iterable<File>,
  maxBytes: number | null,
): ImageFileSelection {
  const accepted: File[] = [];
  const rejected: RejectedImageFile[] = [];

  for (const file of files) {
    if (!isSupportedImageFile(file)) {
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
