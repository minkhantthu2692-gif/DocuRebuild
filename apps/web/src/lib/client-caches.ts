import { LANGUAGE_STORAGE_KEY } from "@/i18n";
import { APPEARANCE_STORAGE_KEY } from "@/lib/appearance";
import { WORKSPACE_LAYOUT_KEY } from "@/lib/workspace-layout";

/**
 * Remove the preferences the renderer caches in localStorage.
 *
 * A factory reset clears the database and data folder; these few keys sit in
 * the renderer instead, so they have to be removed explicitly after the reset
 * succeeds. Failures are ignored because storage can be unavailable and the
 * database is already cleared by that point.
 */
export function clearClientCaches() {
  for (const key of [APPEARANCE_STORAGE_KEY, LANGUAGE_STORAGE_KEY, WORKSPACE_LAYOUT_KEY]) {
    try {
      localStorage.removeItem(key);
    } catch {
      // Nothing else to clear; the reset has already succeeded.
    }
  }
}
