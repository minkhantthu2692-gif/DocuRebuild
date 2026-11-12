/**
 * Read a download name from a Content-Disposition header.
 *
 * Browsers do not expose the server-provided filename for fetch responses, so
 * the header is parsed here. RFC 5987 `filename*` wins because it preserves
 * non-ASCII project names; the quoted `filename` is the portable fallback.
 */
export function filenameFromDisposition(disposition: string | null): string | null {
  if (!disposition) return null;

  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1].trim());
    } catch {
      return null;
    }
  }

  const plain = /filename="?([^";]+)"?/i.exec(disposition);
  return plain ? plain[1].trim() : null;
}

/** Save a blob through a temporary object URL, then release it. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
