import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  AiProbeRequest,
  AiProbeResponse,
  AiProvidersResponse,
  AiRegionProposalsRequest,
  AiRegionProposalsResponse,
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
  status: "pending" | "accepted" | "rejected" | "all" = "pending",
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

/** Accepted and rejected proposals are kept for review; pending ones are shown separately. */
export function usePageAiSuggestionHistory(
  projectId: string,
  pageId: string | null,
  enabled: boolean,
) {
  return useQuery<AiSuggestionsResponse>({
    queryKey: pageAiSuggestionsKey(projectId, pageId ?? "", "all"),
    queryFn: () => api.listAiSuggestions(projectId, pageId as string),
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

/**
 * Ask the configured vision model for region proposals. Nothing is saved, so
 * the response only feeds the reviewable overlay on the source page.
 */
export function useAiRegionProposals(projectId: string, pageId: string | null) {
  const queryClient = useQueryClient();
  return useMutation<
    AiRegionProposalsResponse,
    Error,
    { payload?: AiRegionProposalsRequest }
  >({
    mutationFn: ({ payload }) =>
      api.createAiRegionProposals(projectId, pageId as string, payload ?? {}),
    onSettled: () => {
      // Attempts are counted even when the provider returned nothing usable.
      void queryClient.invalidateQueries({ queryKey: ["ai", "usage"] });
    },
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
      const historyKey = pageAiSuggestionsKey(
        projectId,
        response.suggestion.page_id,
        "all",
      );
      queryClient.setQueryData<AiSuggestionsResponse>(historyKey, (current) => {
        if (!current) return current;
        if (current.suggestions.some((item) => item.id === response.suggestion.id)) {
          return current;
        }
        return { suggestions: [response.suggestion, ...current.suggestions] };
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
      const historyKey = pageAiSuggestionsKey(
        projectId,
        response.suggestion.page_id,
        "all",
      );
      queryClient.setQueryData<AiSuggestionsResponse>(historyKey, (current) => {
        if (!current) return current;
        return {
          suggestions: current.suggestions.map((item) =>
            item.id === response.suggestion.id ? response.suggestion : item,
          ),
        };
      });
    },
  });
}
