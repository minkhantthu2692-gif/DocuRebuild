import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ElementKind, ElementSummary } from "@docurebuild/shared-types";

import { api } from "@/lib/api";

function listKey(projectId: string, pageId: string) {
  return ["elements", projectId, pageId] as const;
}

function replaceElement(
  queryClient: ReturnType<typeof useQueryClient>,
  projectId: string,
  pageId: string,
  element: ElementSummary,
) {
  queryClient.setQueryData<ElementSummary[]>(listKey(projectId, pageId), (current) =>
    (current ?? []).map((item) => (item.id === element.id ? element : item)),
  );
}

// Extracted elements change which regions are still worth suggesting, so a
// cached suggestion list must not survive a crop being added or removed.
function invalidateProposals(
  queryClient: ReturnType<typeof useQueryClient>,
  projectId: string,
  pageId: string,
) {
  void queryClient.invalidateQueries({
    queryKey: ["region-proposals", projectId, pageId],
  });
}

export function useElements(projectId: string, pageId: string | null, enabled = true) {
  return useQuery({
    queryKey: ["elements", projectId, pageId],
    queryFn: () => api.listElements(projectId, pageId as string),
    enabled: enabled && Boolean(pageId),
    staleTime: 10_000,
  });
}

export function useRegionProposals(
  projectId: string,
  pageId: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["region-proposals", projectId, pageId],
    queryFn: () => api.getRegionProposals(projectId, pageId as string),
    enabled: enabled && Boolean(pageId),
    staleTime: 0,
  });
}

export function useCreateElement(projectId: string, pageId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      kind: ElementKind;
      x: number;
      y: number;
      width: number;
      height: number;
      caption: string;
    }) => api.createElement(projectId, pageId, payload),
    onSuccess: (element) => {
      queryClient.setQueryData<ElementSummary[]>(
        listKey(projectId, pageId),
        (current) => [element, ...(current ?? []).filter((item) => item.id !== element.id)],
      );
      invalidateProposals(queryClient, projectId, pageId);
    },
  });
}

export function useUpdateElement(projectId: string, pageId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      elementId,
      ...patch
    }: {
      elementId: string;
      caption?: string;
      verified?: boolean;
    }) => api.updateElement(projectId, elementId, patch),
    onSuccess: (element) => {
      replaceElement(queryClient, projectId, pageId, element);
    },
  });
}

export function useExtractElementText(projectId: string, pageId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      elementId,
      languages,
    }: {
      elementId: string;
      languages: string[];
    }) => api.extractElementText(projectId, elementId, languages),
    onSuccess: (element) => {
      replaceElement(queryClient, projectId, pageId, element);
    },
  });
}

export function useUpdateElementText(projectId: string, pageId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ elementId, text }: { elementId: string; text: string }) =>
      api.updateElementText(projectId, elementId, text),
    onSuccess: (element) => {
      replaceElement(queryClient, projectId, pageId, element);
    },
  });
}

export function useDeleteElement(projectId: string, pageId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (elementId: string) => api.deleteElement(projectId, elementId),
    onSuccess: (_result, elementId) => {
      queryClient.setQueryData<ElementSummary[]>(
        listKey(projectId, pageId),
        (current) => (current ?? []).filter((item) => item.id !== elementId),
      );
      invalidateProposals(queryClient, projectId, pageId);
    },
  });
}
