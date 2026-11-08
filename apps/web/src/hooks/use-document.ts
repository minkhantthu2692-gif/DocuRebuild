import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { JSONContent } from "@docurebuild/shared-types";

import { api } from "@/lib/api";

export function useDocument(projectId: string | undefined) {
  return useQuery({
    queryKey: ["document", projectId],
    queryFn: () => api.getDocument(projectId as string),
    enabled: Boolean(projectId),
    // The editor owns the working copy once loaded; refetching underneath an
    // active editing session would discard keystrokes.
    staleTime: Infinity,
    retry: 1,
  });
}

export interface SaveDocumentPayload {
  content: JSONContent;
  plainText: string;
}

export function useSaveDocument(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ content, plainText }: SaveDocumentPayload) =>
      api.saveDocument(projectId, content, plainText),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
