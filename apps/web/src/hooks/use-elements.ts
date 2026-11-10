import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ElementKind, ElementSummary } from "@docurebuild/shared-types";

import { api } from "@/lib/api";

function listKey(projectId: string, pageId: string) {
  return ["elements", projectId, pageId] as const;
}

export function useElements(projectId: string, pageId: string | null, enabled = true) {
  return useQuery({
    queryKey: ["elements", projectId, pageId],
    queryFn: () => api.listElements(projectId, pageId as string),
    enabled: enabled && Boolean(pageId),
    staleTime: 10_000,
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
      queryClient.setQueryData<ElementSummary[]>(
        listKey(projectId, pageId),
        (current) =>
          (current ?? []).map((item) => (item.id === element.id ? element : item)),
      );
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
    },
  });
}
