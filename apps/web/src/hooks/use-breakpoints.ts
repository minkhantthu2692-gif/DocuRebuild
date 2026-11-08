import { useMediaQuery } from "@/hooks/use-media-query";

export function useIsDesktop() {
  return useMediaQuery("(min-width: 1024px)");
}

export function useIsTablet() {
  return useMediaQuery("(min-width: 640px)");
}
