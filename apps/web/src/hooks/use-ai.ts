import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  AiProbeRequest,
  AiProbeResponse,
  AiProvidersResponse,
  AiSuggestionCreate,
  AiSuggestionDecisionInput,
  AiSuggestionDecisionResponse,
} from "@docurebuild/shared-types";

import { latestOcrKey } from "@/hooks/use-ocr";
import { api } from "@/lib/api";

export function useAiProviders() {
  return useQuery<AiProvidersResponse>({
    queryKey: ["ai", "providers"],
    queryFn: api.listAiProviders,
    staleTime: Infinity,
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
    },
  });
}
