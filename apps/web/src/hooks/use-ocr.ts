import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { OcrRun } from "@docurebuild/shared-types";

import { api } from "@/lib/api";

export function latestOcrKey(projectId: string, pageId: string) {
  return ["ocr", "latest", projectId, pageId] as const;
}

const latestKey = latestOcrKey;

export function useOcrCapabilities() {
  return useQuery({
    queryKey: ["ocr", "capabilities"],
    queryFn: () => api.getOcrCapabilities(),
    staleTime: 15_000,
    retry: 1,
  });
}

export function useLatestOcr(projectId: string, pageId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["ocr", "latest", projectId, pageId],
    queryFn: () => api.getLatestOcr(projectId, pageId as string),
    enabled: enabled && Boolean(pageId),
    refetchInterval: (query) => {
      const run = query.state.data as OcrRun | null | undefined;
      return run &&
        (run.status === "queued" ||
          run.status === "running" ||
          run.status === "cancelling")
        ? 900
        : false;
    },
  });
}

export function useStartOcr(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      pageId,
      languages,
      pageSegmentationMode,
    }: {
      pageId: string;
      languages: string[];
      pageSegmentationMode?: number;
    }) => api.startOcr(projectId, pageId, languages, pageSegmentationMode),
    onSuccess: (run) => {
      queryClient.setQueryData(latestKey(projectId, run.page_id), run);
    },
  });
}

export function useCancelOcr(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => api.cancelOcr(projectId, runId),
    onSuccess: (run) => {
      queryClient.setQueryData(latestKey(projectId, run.page_id), run);
    },
  });
}

export function useUpdateOcrBlock(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      pageId,
      blockId,
      text,
      verified,
    }: {
      pageId: string;
      blockId: string;
      text?: string;
      verified?: boolean;
    }) => api.updateOcrBlock(projectId, pageId, blockId, { text, verified }),
    onSuccess: (run) => {
      queryClient.setQueryData(latestKey(projectId, run.page_id), run);
    },
  });
}
