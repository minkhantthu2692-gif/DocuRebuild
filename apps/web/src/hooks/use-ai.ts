import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  AiConnectionDetail,
  AiConnectionPatch,
  AiConnectionTestRequest,
  AiConnectionTestResponse,
  AiConnectionCreate,
  AiConnectionsResponse,
  AiCostClass,
  AiKey,
  AiKeyCreate,
  AiKeyPatch,
  AiManualModelCreate,
  AiMigrationStatus,
  AiModelFavoriteInput,
  AiModel,
  AiOverview,
  AiPreferences,
  AiPreferencesPatch,
  AiProvidersResponse,
  AiRegionProposalsRequest,
  AiRegionProposalsResponse,
  AiRouteTask,
  AiRouteUpdate,
  AiRoutesResponse,
  AiSuggestionBulkInput,
  AiSuggestionBulkResponse,
  AiSuggestionCreate,
  AiSuggestionDecisionInput,
  AiSuggestionDecisionResponse,
  AiSuggestionsResponse,
  AiTasksResponse,
  AiUsageHistoryResponse,
  AiUsageOutcome,
  AiUsageResponse,
  AiUsageTask,
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

export function projectAiSuggestionsKey(
  projectId: string,
  status: "pending" | "accepted" | "rejected" | "all" = "pending",
) {
  return ["ai", "suggestions", projectId, "project", status] as const;
}

/** Pending proposals across every page, for the project-wide review queue. */
export function useProjectAiSuggestions(
  projectId: string,
  status: "pending" | "all" = "pending",
  enabled = true,
) {
  return useQuery<AiSuggestionsResponse>({
    queryKey: projectAiSuggestionsKey(projectId, status),
    queryFn: () =>
      api.listProjectAiSuggestions(
        projectId,
        status === "all" ? undefined : status,
      ),
    enabled,
    staleTime: 0,
    refetchOnMount: "always",
    retry: 1,
  });
}

export function useAiProviders() {
  return useQuery<AiProvidersResponse>({
    queryKey: ["ai", "providers"],
    queryFn: api.listAiProviders,
    staleTime: Infinity,
    retry: 1,
  });
}

export function useAiConnections() {
  return useQuery<AiConnectionsResponse>({
    queryKey: ["ai", "connections"],
    queryFn: api.listAiConnections,
    staleTime: 5_000,
    retry: 1,
  });
}

export function useAiConnection(connectionId: string | null) {
  return useQuery<AiConnectionDetail>({
    queryKey: ["ai", "connections", connectionId],
    queryFn: () => api.getAiConnection(connectionId as string),
    enabled: Boolean(connectionId),
    staleTime: 5_000,
    retry: 1,
  });
}

export function useAiModels(
  connectionId: string | null,
  params: {
    query?: string;
    capability?: "text" | "vision";
    favoritesOnly?: boolean;
    availableOnly?: boolean;
  } = {},
  enabled = true,
) {
  return useQuery<AiModel[]>({
    queryKey: ["ai", "models", connectionId, params],
    queryFn: () => api.listAiModels(connectionId, params),
    enabled: enabled && Boolean(connectionId),
    staleTime: 15_000,
    retry: 1,
  });
}

export function useAiRoutes() {
  return useQuery<AiRoutesResponse>({
    queryKey: ["ai", "routes"],
    queryFn: api.listAiRoutes,
    staleTime: 5_000,
    retry: 1,
  });
}

/** Per-task readiness used by workspace actions to enable or explain AI buttons. */
export function useAiTasks() {
  return useQuery<AiTasksResponse>({
    queryKey: ["ai", "tasks"],
    queryFn: api.getAiTasks,
    staleTime: 5_000,
    retry: 1,
  });
}

export function useAiMigration() {
  return useQuery<AiMigrationStatus>({
    queryKey: ["ai", "migration"],
    queryFn: api.getAiMigration,
    staleTime: 30_000,
    retry: 1,
  });
}

export function useAiPreferences() {
  return useQuery<AiPreferences>({
    queryKey: ["ai", "preferences"],
    queryFn: api.getAiPreferences,
    staleTime: 15_000,
    retry: 1,
  });
}

export function useAiOverview(enabled = true) {
  return useQuery<AiOverview>({
    queryKey: ["ai", "overview"],
    queryFn: api.getAiOverview,
    enabled,
    staleTime: 15_000,
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

export interface AiUsageHistoryParams {
  limit: number;
  offset: number;
  outcome?: AiUsageOutcome;
  task?: AiUsageTask;
  connectionId?: string;
}

export function useAiUsageHistory(params: AiUsageHistoryParams, enabled = true) {
  return useQuery<AiUsageHistoryResponse>({
    queryKey: ["ai", "usage", "history", params],
    queryFn: () => api.getAiUsageHistory(params),
    enabled,
    staleTime: 0,
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

/**
 * Ask the routed vision model for region proposals. Nothing is saved, so the
 * response only feeds the reviewable overlay on the source page.
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
      void queryClient.invalidateQueries({
        queryKey: projectAiSuggestionsKey(projectId, "pending"),
      });
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
      // The project-wide queue lists pending proposals only.
      void queryClient.invalidateQueries({
        queryKey: projectAiSuggestionsKey(projectId, "pending"),
      });
    },
  });
}

/**
 * Decide several pending proposals in one request.
 *
 * The backend revalidates each proposal separately, so a stale item is reported
 * as failed while the rest still change. Refreshing every proposal query for the
 * project keeps an open page dialog and the project queue in sync.
 */
export function useBulkDecideAiSuggestions(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation<
    AiSuggestionBulkResponse,
    Error,
    AiSuggestionBulkInput
  >({
    mutationFn: (payload) => api.decideAiSuggestionsBulk(projectId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["ai", "suggestions", projectId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["ocr", "latest", projectId],
      });
    },
  });
}

/* -------------------------------------------------------------------------- */
/*                       Connection and credential actions                    */
/* -------------------------------------------------------------------------- */

function useInvalidateAi() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["ai"] });
  };
}

export function useCreateAiConnection() {
  const invalidate = useInvalidateAi();
  return useMutation<AiConnectionDetail, Error, AiConnectionCreate>({
    mutationFn: api.createAiConnection,
    onSuccess: invalidate,
  });
}

export function useUpdateAiConnection(connectionId: string) {
  const invalidate = useInvalidateAi();
  return useMutation<AiConnectionDetail, Error, AiConnectionPatch>({
    mutationFn: (payload) => api.updateAiConnection(connectionId, payload),
    onSuccess: invalidate,
  });
}

export function useDeleteAiConnection() {
  const invalidate = useInvalidateAi();
  return useMutation<void, Error, string>({
    mutationFn: api.deleteAiConnection,
    onSuccess: invalidate,
  });
}

export function useTestAiConnection(connectionId: string) {
  const invalidate = useInvalidateAi();
  return useMutation<
    AiConnectionTestResponse,
    Error,
    AiConnectionTestRequest | undefined
  >({
    mutationFn: (payload) => api.testAiConnection(connectionId, payload ?? {}),
    onSuccess: invalidate,
  });
}

export function useAddAiKey(connectionId: string) {
  const invalidate = useInvalidateAi();
  return useMutation<AiKey, Error, AiKeyCreate>({
    mutationFn: (payload) => api.addAiKey(connectionId, payload),
    onSuccess: invalidate,
  });
}

export function useUpdateAiKey(connectionId: string) {
  const invalidate = useInvalidateAi();
  return useMutation<
    AiKey,
    Error,
    { keyId: string; payload: AiKeyPatch }
  >({
    mutationFn: ({ keyId, payload }) => api.updateAiKey(connectionId, keyId, payload),
    onSuccess: invalidate,
  });
}

export function useDeleteAiKey(connectionId: string) {
  const invalidate = useInvalidateAi();
  return useMutation<void, Error, string>({
    mutationFn: (keyId) => api.deleteAiKey(connectionId, keyId),
    onSuccess: invalidate,
  });
}

export function useAddAiModel(connectionId: string) {
  const invalidate = useInvalidateAi();
  return useMutation<AiModel, Error, AiManualModelCreate>({
    mutationFn: (payload) => api.addAiModel(connectionId, payload),
    onSuccess: invalidate,
  });
}

export function useFavoriteAiModel(connectionId: string) {
  const invalidate = useInvalidateAi();
  return useMutation<AiModel, Error, AiModelFavoriteInput>({
    mutationFn: (payload) => api.favoriteAiModel(connectionId, payload),
    onSuccess: invalidate,
  });
}

export function useUpdateAiRoute() {
  const invalidate = useInvalidateAi();
  return useMutation<unknown, Error, { task: AiRouteTask; payload: AiRouteUpdate }>({
    mutationFn: ({ task, payload }) => api.updateAiRoute(task, payload),
    onSuccess: invalidate,
  });
}

export function useUpdateAiPreferences() {
  const invalidate = useInvalidateAi();
  return useMutation<AiPreferences, Error, AiPreferencesPatch>({
    mutationFn: api.updateAiPreferences,
    onSuccess: invalidate,
  });
}

export function useClearAiUsage() {
  const invalidate = useInvalidateAi();
  return useMutation<void, Error, void>({
    mutationFn: api.clearAiUsage,
    onSuccess: invalidate,
  });
}

export type { AiCostClass };
