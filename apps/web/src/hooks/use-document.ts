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

export function useDocumentRevisions(projectId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["document-revisions", projectId],
    queryFn: () => api.listDocumentRevisions(projectId as string),
    enabled: Boolean(projectId) && enabled,
    retry: 1,
  });
}

export function useDocumentRevision(
  projectId: string,
  revisionId: string | null,
) {
  return useQuery({
    queryKey: ["document-revision", projectId, revisionId],
    queryFn: () => api.getDocumentRevision(projectId, revisionId as string),
    enabled: Boolean(revisionId),
    retry: 1,
  });
}

export function useCreateDocumentRevision(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.createDocumentRevision(projectId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["document-revisions", projectId],
      });
    },
  });
}

export function useRestoreDocumentRevision(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (revisionId: string) =>
      api.restoreDocumentRevision(projectId, revisionId),
    onSuccess: (record) => {
      // The editor applies the restored content directly; keep the cache in sync
      // so a later remount does not show the replaced document.
      queryClient.setQueryData(["document", projectId], record);
      void queryClient.invalidateQueries({
        queryKey: ["document-revisions", projectId],
      });
      void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
