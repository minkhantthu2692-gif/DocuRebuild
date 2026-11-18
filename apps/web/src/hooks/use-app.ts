import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  AiProfilePatch,
  AiProfileSettings,
  AppSettings,
} from "@docurebuild/shared-types";

import { api, type SettingsPatch } from "@/lib/api";

export function useAppMeta() {
  return useQuery({
    queryKey: ["meta"],
    queryFn: api.meta,
    staleTime: Infinity,
    retry: 1,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    staleTime: 15_000,
    refetchInterval: 60_000,
    retry: false,
  });
}

export function useAppSettings() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: api.getSettings,
    staleTime: Infinity,
    retry: 1,
  });
}

function mergeAiProfile(
  saved: AiProfileSettings,
  patch: AiProfilePatch | undefined,
): AiProfileSettings {
  if (!patch) return saved;
  const { api_key, clear_api_key, ...profile } = patch;
  return {
    ...saved,
    ...profile,
    has_api_key: api_key ? true : clear_api_key ? false : saved.has_api_key,
  };
}

function mergeSettings(current: AppSettings | undefined, patch: SettingsPatch): AppSettings {
  const base: AppSettings = current ?? {
    language: "en",
    appearance: {
      theme: "system",
      accent: "indigo",
      radius: "soft",
      blur: "subtle",
      density: "comfortable",
      font_size: "md",
      motion: "full",
    },
    editor: { document_font: "serif" },
    export: { pdf_page_size: "a4", pdf_margin: "normal" },
    ai: {
      text: {
        provider: "ollama",
        base_url: "",
        model: "",
        allow_remote: false,
        has_api_key: false,
      },
      vision: {
        provider: "ollama",
        base_url: "",
        model: "",
        allow_remote: false,
        has_api_key: false,
      },
      request_limit: 0,
    },
    backups: { auto_on_open: false, interval_hours: 24, keep_copies: 5 },
  };
  return {
    ...base,
    ...(patch.language ? { language: patch.language } : {}),
    appearance: { ...base.appearance, ...patch.appearance },
    editor: { ...base.editor, ...patch.editor },
    export: { ...base.export, ...patch.export },
    ai: {
      text: mergeAiProfile(base.ai.text, patch.ai?.text),
      vision: mergeAiProfile(base.ai.vision, patch.ai?.vision),
      request_limit: patch.ai?.request_limit ?? base.ai.request_limit,
    },
    backups: { ...base.backups, ...patch.backups },
  };
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: SettingsPatch) => api.updateSettings(patch),
    onMutate: async (patch) => {
      await queryClient.cancelQueries({ queryKey: ["settings"] });
      const previous = queryClient.getQueryData<AppSettings>(["settings"]);
      queryClient.setQueryData<AppSettings>(["settings"], mergeSettings(previous, patch));
      return { previous };
    },
    onError: (_error, _patch, context) => {
      if (context?.previous) {
        queryClient.setQueryData(["settings"], context.previous);
      }
    },
    onSuccess: (settings) => {
      queryClient.setQueryData(["settings"], settings);
    },
  });
}
