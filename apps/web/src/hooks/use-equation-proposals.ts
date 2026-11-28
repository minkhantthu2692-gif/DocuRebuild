import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export function pageEquationProposalsKey(projectId: string, pageId: string | null) {
  return ["equations", "page", projectId, pageId] as const;
}

export function usePageEquationProposals(
  projectId: string,
  pageId: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: pageEquationProposalsKey(projectId, pageId),
    queryFn: () => api.getPageEquationProposals(projectId, pageId as string),
    enabled: enabled && Boolean(pageId),
    staleTime: 30_000,
    retry: false,
  });
}
