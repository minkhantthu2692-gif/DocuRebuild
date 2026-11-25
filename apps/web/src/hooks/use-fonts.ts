import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { FontsResponse } from "@docurebuild/shared-types";

import { api } from "@/lib/api";

export const FONTS_QUERY_KEY = ["fonts"] as const;

export function useFonts() {
  return useQuery({
    queryKey: FONTS_QUERY_KEY,
    queryFn: () => api.listFonts(),
    // The backend caches the directory scan. The dialog exposes an explicit
    // refresh so a font installed in Windows can appear without a restart.
    staleTime: 2 * 60_000,
    retry: 1,
  });
}

export function useRefreshFonts() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.listFonts(true),
    onSuccess: (data: FontsResponse) => {
      queryClient.setQueryData(FONTS_QUERY_KEY, data);
    },
  });
}

export function useImportFont() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => api.importFont(file),
    onSettled: () => {
      // A duplicate upload returns the existing face, but the catalogue still
      // needs to reflect any newly imported family.
      void queryClient.invalidateQueries({ queryKey: FONTS_QUERY_KEY });
    },
  });
}

export function useDeleteFont() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (fontId: string) => api.deleteFont(fontId),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: FONTS_QUERY_KEY });
    },
  });
}
