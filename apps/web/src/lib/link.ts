const ALLOWED_PROTOCOLS = new Set(["http:", "https:", "mailto:"]);

/**
 * Normalise a user-entered link target.
 *
 * Only `http`, `https` and `mailto` are accepted so a pasted or typed
 * `javascript:`/`data:` target can never enter the document. A bare domain is
 * upgraded to `https://`; anything ambiguous is rejected instead of guessed.
 */
export function normalizeLinkUrl(input: string): string | null {
  const value = input.trim();
  if (!value || /\s/.test(value) || value.startsWith("//")) return null;

  const hasScheme = /^[a-z][a-z0-9+.-]*:/i.test(value);
  if (hasScheme) {
    try {
      const parsed = new URL(value);
      if (!ALLOWED_PROTOCOLS.has(parsed.protocol)) return null;
      return value;
    } catch {
      return null;
    }
  }

  if (!value.includes(".")) return null;
  const candidate = `https://${value}`;
  try {
    const parsed = new URL(candidate);
    return parsed.hostname.includes(".") ? candidate : null;
  } catch {
    return null;
  }
}
