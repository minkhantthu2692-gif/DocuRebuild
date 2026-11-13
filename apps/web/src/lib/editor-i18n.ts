import { i18n } from "@/i18n";

/**
 * Translate a workspace string with a literal fallback.
 *
 * Node views can render before the i18n singleton is initialized (for example in
 * a unit test), so interpolation is applied to the fallback in that case instead
 * of showing a raw `{{n}}` placeholder.
 */
export function translateWorkspace(
  key: string,
  fallback: string,
  options?: Record<string, unknown>,
): string {
  if (!i18n.isInitialized) {
    return fallback.replace(/\{\{(\w+)\}\}/g, (match, name: string) =>
      options && name in options ? String(options[name]) : match,
    );
  }
  const value = i18n.t(key, { ns: "workspace", defaultValue: fallback, ...options });
  return typeof value === "string" && value ? value : fallback;
}
