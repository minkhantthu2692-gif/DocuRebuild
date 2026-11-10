import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { PageSummary, PageEdits } from "@docurebuild/shared-types";

import { api, type ProjectCreatePayload } from "@/lib/api";

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: api.listProjects,
  });
}

export function useProject(projectId: string | undefined) {
  return useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(projectId as string),
    enabled: Boolean(projectId),
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProjectCreatePayload) => api.createProject(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useUpdateProject(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name?: string; description?: string }) =>
      api.updateProject(projectId, payload),
    onSuccess: (project) => {
      queryClient.setQueryData(["project", projectId], project);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useDeleteProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => api.deleteProject(projectId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useOpenProject(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.openProject(projectId),
    onSuccess: (project) => {
      queryClient.setQueryData(["project", projectId], project);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function usePages(projectId: string | undefined) {
  return useQuery({
    queryKey: ["pages", projectId],
    queryFn: () => api.listPages(projectId as string),
    enabled: Boolean(projectId),
  });
}

export function useImportPages(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (files: File[]) => api.importPages(projectId, files),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pages", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useRotatePage(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ pageId, degrees }: { pageId: string; degrees: number }) =>
      api.rotatePage(projectId, pageId, degrees),
    onSuccess: (page) => {
      queryClient.setQueryData<PageSummary[]>(["pages", projectId], (current) =>
        current?.map((item) => (item.id === page.id ? page : item)),
      );
      void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });
}

export function useDeletePage(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (pageId: string) => api.deletePage(projectId, pageId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pages", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useReorderPages(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (pageIds: string[]) => api.reorderPages(projectId, pageIds),
    onSuccess: (pages) => {
      queryClient.setQueryData(["pages", projectId], pages);
    },
  });
}

export function useUpdatePageEdits(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ pageId, edits }: { pageId: string; edits: PageEdits }) =>
      api.updatePageEdits(projectId, pageId, edits),
    onSuccess: (page) => {
      queryClient.setQueryData<PageSummary[]>(["pages", projectId], (current) =>
        current?.map((item) => (item.id === page.id ? page : item)),
      );
      void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });
}

export function useResetPageEdits(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (pageId: string) => api.resetPageEdits(projectId, pageId),
    onSuccess: (page) => {
      queryClient.setQueryData<PageSummary[]>(["pages", projectId], (current) =>
        current?.map((item) => (item.id === page.id ? page : item)),
      );
      void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });
}

export function useEstimatePageSkew(projectId: string) {
  return useMutation({
    mutationFn: (pageId: string) => api.estimatePageSkew(projectId, pageId),
  });
}
