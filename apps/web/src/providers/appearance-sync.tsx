import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { DEFAULT_APPEARANCE, applyAppearance, cacheAppearance, readCachedAppearance } from "@/lib/appearance";
import { cacheLanguage, resolveLanguage } from "@/i18n";
import { useAppSettings } from "@/hooks/use-app";

/**
 * Keeps the DOM, cached theme and i18next in sync with persisted settings.
 * Renders nothing.
 */
export function AppearanceSync() {
  const { data: settings } = useAppSettings();
  const { i18n } = useTranslation();
  const appearance = settings?.appearance ?? readCachedAppearance() ?? DEFAULT_APPEARANCE;

  useEffect(() => {
    applyAppearance(appearance);
    cacheAppearance(appearance);
  }, [
    appearance,
    appearance.theme,
    appearance.accent,
    appearance.radius,
    appearance.blur,
    appearance.density,
    appearance.font_size,
    appearance.motion,
  ]);

  useEffect(() => {
    if (appearance.theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = () => applyAppearance(appearance);
    media.addEventListener("change", handleChange);
    return () => media.removeEventListener("change", handleChange);
  }, [appearance]);

  useEffect(() => {
    const resolved = resolveLanguage(settings?.language);
    cacheLanguage(resolved);
    document.documentElement.lang = resolved;
    if (i18n.language !== resolved) {
      void i18n.changeLanguage(resolved);
    }
  }, [settings?.language, i18n]);

  return null;
}
