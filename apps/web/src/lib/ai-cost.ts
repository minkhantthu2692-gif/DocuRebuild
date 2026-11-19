import type { AiCostClass } from "@docurebuild/shared-types";

/**
 * Report whether a configured AI server runs on this device.
 *
 * An empty URL uses the provider's loopback default, so it counts as local.
 * This only mirrors the backend rule for UI decisions; the backend remains the
 * authority and refuses paid requests without confirmation.
 */
export function isLoopbackUrl(value: string | null | undefined): boolean {
  const trimmed = (value ?? "").trim();
  if (!trimmed) return true;
  try {
    const hostname = new URL(trimmed).hostname.toLowerCase().replace(/^\[|\]$/g, "");
    return (
      hostname === "localhost" ||
      hostname.endsWith(".localhost") ||
      hostname === "::1" ||
      hostname.startsWith("127.")
    );
  } catch {
    return false;
  }
}

export interface AiCostTarget {
  base_url?: string | null;
  cost_class?: AiCostClass | null;
}

/**
 * A remote connection needs approval unless the user declared a free tier.
 *
 * The task router resolves the effective cost class, so the UI only has to look
 * at it. "local" never applies to a remote host: the backend coerces that
 * combination to paid, so the UI must ask before sending the request.
 */
export function needsPaidApproval(target: AiCostTarget | undefined): boolean {
  if (!target) return false;
  if (isLoopbackUrl(target.base_url)) return false;
  return target.cost_class !== "free";
}
