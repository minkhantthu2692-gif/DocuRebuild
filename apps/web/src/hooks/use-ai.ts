import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  AiProbeRequest,
  AiProbeResponse,
  AiProvidersResponse,
  AiSuggestionCreate,
  AiSuggestionDecisionInput,
  AiSuggestionDecisionResponse,
  AiSuggestionsResponse,
  AiUsageResponse,
} from "@docurebuild/shared-types";

import { latestOcrKey } from "@/hooks/use-ocr";
import { api } from "@/lib/api";

export function pageAiSuggestionsKey(
  projectId: string,
  pageId: string,
  status: "pending" | "accepted" | "rejected" = "pending",
) {
  return ["ai", "suggestions", projectId, pageId, status] as const;
}

export function useAiProviders() {
  return useQuery<AiProvidersResponse>({
    queryKey: ["ai", "providers"],
    queryFn: api.listAiProviders,
    staleTime: Infinity,
    retry: 1,
  });
}

export function useAiUsage(enabled = true) {
  return useQuery<AiUsageResponse>({
    queryKey: ["ai", "usage"],
    queryFn: api.getAiUsage,
    enabled,
    staleTime: 15_000,
    retry: 1,
  });
}

export function usePageAiSuggestions(
  projectId: string,
  pageId: string | null,
  enabled: boolean,
) {
  return useQuery<AiSuggestionsResponse>({
    queryKey: pageAiSuggestionsKey(projectId, pageId ?? "", "pending"),
    queryFn: () => api.listAiSuggestions(projectId, pageId as string, "pending"),
    enabled: enabled && Boolean(pageId),
    staleTime: 0,
    refetchOnMount: "always",
    retry: 1,
  });
}

export function useProbeAiProvider() {
  return useMutation<AiProbeResponse, Error, AiProbeRequest>({
    mutationFn: api.probeAiProvider,
  });
}

export function useCreateAiSuggestion(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation<
    AiSuggestionDecisionResponse,
    Error,
    { pageId: string; blockId: string; payload?: AiSuggestionCreate }
  >({
    mutationFn: ({ pageId, blockId, payload }) =>
      api.createAiCleanupSuggestion(projectId, pageId, blockId, payload ?? {}),
    onSuccess: (response) => {
      queryClient.setQueryData(
        latestOcrKey(projectId, response.run.page_id),
        response.run,
      );
      const key = pageAiSuggestionsKey(
        projectId,
        response.suggestion.page_id,
        "pending",
      );
      queryClient.setQueryData<AiSuggestionsResponse>(key, (current) => {
        const suggestions = current?.suggestions ?? [];
        if (suggestions.some((item) => item.id === response.suggestion.id)) {
          return current;
        }
        return { suggestions: [response.suggestion, ...suggestions] };
      });
      void queryClient.invalidateQueries({ queryKey: ["ai", "usage"] });
    },
    onError: () => {
      // Failed requests are still counted when the provider was contacted.
      void queryClient.invalidateQueries({ queryKey: ["ai", "usage"] });
    },
  });
}

export function useDecideAiSuggestion(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation<
    AiSuggestionDecisionResponse,
    Error,
    { suggestionId: string; payload: AiSuggestionDecisionInput }
  >({
    mutationFn: ({ suggestionId, payload }) =>
      api.decideAiSuggestion(projectId, suggestionId, payload),
    onSuccess: (response) => {
      queryClient.setQueryData(
        latestOcrKey(projectId, response.run.page_id),
        response.run,
      );
      const key = pageAiSuggestionsKey(
        projectId,
        response.suggestion.page_id,
        "pending",
      );
      queryClient.setQueryData<AiSuggestionsResponse>(key, (current) => {
        if (!current) return current;
        return {
          suggestions: current.suggestions.filter(
            (item) => item.id !== response.suggestion.id,
          ),
        };
      });
    },
  });
}
