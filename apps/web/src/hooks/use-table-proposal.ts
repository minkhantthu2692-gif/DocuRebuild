import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export function tableProposalKey(
  projectId: string,
  pageId: string | null,
  blockId: string | null,
) {
  return ["tables", "proposal", projectId, pageId, blockId] as const;
}

export function useTableProposal(
  projectId: string,
  pageId: string | null,
  blockId: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: tableProposalKey(projectId, pageId, blockId),
    queryFn: () => api.getTableProposal(projectId, pageId as string, blockId as string),
    enabled: enabled && Boolean(pageId) && Boolean(blockId),
    staleTime: 30_000,
    // A refusal (for example "re-run OCR") is a stable answer, not a transient
    // failure, so retrying would only delay the message.
    retry: false,
  });
}

export function pageTableProposalsKey(projectId: string, pageId: string | null) {
  return ["tables", "page", projectId, pageId] as const;
}

export function usePageTableProposals(
  projectId: string,
  pageId: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: pageTableProposalsKey(projectId, pageId),
    queryFn: () => api.getPageTableProposals(projectId, pageId as string),
    enabled: enabled && Boolean(pageId),
    staleTime: 30_000,
    retry: false,
  });
}
