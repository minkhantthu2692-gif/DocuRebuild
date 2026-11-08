import type { AppearanceSettings } from "@docurebuild/shared-types";

export const APPEARANCE_STORAGE_KEY = "docurebuild.appearance";

export const DEFAULT_APPEARANCE: AppearanceSettings = {
  theme: "system",
  accent: "indigo",
  radius: "soft",
  blur: "subtle",
  density: "comfortable",
  font_size: "md",
  motion: "full",
};

export function resolveTheme(theme: AppearanceSettings["theme"]): "light" | "dark" {
  if (theme === "light") return "light";
  if (theme === "dark") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyAppearance(appearance: AppearanceSettings) {
  const root = document.documentElement;
  root.dataset.accent = appearance.accent;
  root.dataset.radius = appearance.radius;
  root.dataset.blur = appearance.blur;
  root.dataset.density = appearance.density;
  root.dataset.fontSize = appearance.font_size;
  root.dataset.motion = appearance.motion;
  root.classList.toggle("dark", resolveTheme(appearance.theme) === "dark");
}

export function cacheAppearance(appearance: AppearanceSettings) {
  try {
    localStorage.setItem(APPEARANCE_STORAGE_KEY, JSON.stringify(appearance));
  } catch {
    /* Storage can be unavailable in private windows; the app still works. */
  }
}

export function readCachedAppearance(): AppearanceSettings | null {
  try {
    const raw = localStorage.getItem(APPEARANCE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AppearanceSettings>;
    return { ...DEFAULT_APPEARANCE, ...parsed };
  } catch {
    return null;
  }
}

export function applyCachedAppearance() {
  const cached = readCachedAppearance();
  if (cached) applyAppearance(cached);
  else applyAppearance(DEFAULT_APPEARANCE);
}
