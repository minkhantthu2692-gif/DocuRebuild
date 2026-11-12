import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ImportJob, PageSummary, PageEdits } from "@docurebuild/shared-types";

import { api, type ProjectCreatePayload } from "@/lib/api";

const ACTIVE_IMPORT_STATUSES: ReadonlySet<ImportJob["status"]> = new Set([
  "queued",
  "running",
  "cancelling",
]);

function isImportActive(job: ImportJob | null | undefined): boolean {
  return Boolean(job && ACTIVE_IMPORT_STATUSES.has(job.status));
}

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

export function useDownloadProjectBackup() {
  return useMutation({
    mutationFn: (projectId: string) => api.downloadProjectBackup(projectId),
  });
}

export function useRestoreProjectBackup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => api.restoreProjectBackup(file),
    onSuccess: (project) => {
      queryClient.setQueryData(["project", project.id], project);
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

export function useProjectHistory(projectId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["project-history", projectId],
    queryFn: () => api.listProjectHistory(projectId as string),
    enabled: Boolean(projectId) && enabled,
    retry: 1,
  });
}

export function usePages(projectId: string | undefined) {
  return useQuery({
    queryKey: ["pages", projectId],
    queryFn: () => api.listPages(projectId as string),
    enabled: Boolean(projectId),
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

export function useStartImport(projectId: string) {
  return useMutation({
    mutationFn: (files: File[]) => api.startImport(projectId, files),
  });
}

export function useImportJob(projectId: string, jobId: string | null) {
  return useQuery({
    queryKey: ["import-job", projectId, jobId],
    queryFn: () => api.getImportJob(projectId, jobId as string),
    enabled: Boolean(jobId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) =>
      isImportActive(query.state.data) ? 500 : false,
  });
}

export function useImportJobs(projectId: string) {
  return useQuery({
    queryKey: ["import-jobs", projectId],
    queryFn: () => api.listImportJobs(projectId, 5),
    refetchOnWindowFocus: false,
    staleTime: 5_000,
  });
}

export function useCancelImportJob(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => api.cancelImportJob(projectId, jobId),
    onSuccess: (job) => {
      queryClient.setQueryData(["import-job", projectId, job.id], job);
    },
  });
}
