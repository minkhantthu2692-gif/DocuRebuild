import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import type { LanguageCode } from "@docurebuild/shared-types";

import enCommon from "./locales/en/common.json";
import enDashboard from "./locales/en/dashboard.json";
import enErrors from "./locales/en/errors.json";
import enSettings from "./locales/en/settings.json";
import enWorkspace from "./locales/en/workspace.json";
import myCommon from "./locales/my/common.json";
import myDashboard from "./locales/my/dashboard.json";
import myErrors from "./locales/my/errors.json";
import mySettings from "./locales/my/settings.json";
import myWorkspace from "./locales/my/workspace.json";

export const NAMESPACES = ["common", "dashboard", "workspace", "settings", "errors"] as const;
export const SUPPORTED_LANGUAGES = ["en", "my"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

const LANGUAGE_STORAGE_KEY = "docurebuild.language";

export const resources = {
  en: {
    common: enCommon,
    dashboard: enDashboard,
    workspace: enWorkspace,
    settings: enSettings,
    errors: enErrors,
  },
  my: {
    common: myCommon,
    dashboard: myDashboard,
    workspace: myWorkspace,
    settings: mySettings,
    errors: myErrors,
  },
} as const;

export function detectSystemLanguage(): SupportedLanguage {
  const candidates = [
    ...(navigator.languages ?? []),
    navigator.language ?? "",
  ];
  return candidates.some((language) => language.toLowerCase().startsWith("my")) ? "my" : "en";
}

export function resolveLanguage(preference: LanguageCode | undefined): SupportedLanguage {
  if (preference === "my") return "my";
  if (preference === "en") return "en";
  return detectSystemLanguage();
}

export function initI18n() {
  if (i18n.isInitialized) return i18n;

  const cached = localStorage.getItem(LANGUAGE_STORAGE_KEY);
  const initial: SupportedLanguage = cached === "my" ? "my" : "en";

  void i18n.use(initReactI18next).init({
    resources,
    lng: initial,
    fallbackLng: "en",
    ns: [...NAMESPACES],
    defaultNS: "common",
    interpolation: { escapeValue: false },
    returnNull: false,
  });

  return i18n;
}

export function cacheLanguage(language: SupportedLanguage) {
  localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
}

export { i18n };
