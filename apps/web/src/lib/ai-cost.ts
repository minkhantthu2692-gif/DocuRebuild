import type { AiProfileSettings } from "@docurebuild/shared-types";

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

/**
 * A remote profile needs approval unless the user declared a free tier.
 *
 * "local" never applies to a remote host: the backend coerces that combination
 * to paid, so the UI must ask before sending the request.
 */
export function needsPaidApproval(
  profile: Pick<AiProfileSettings, "base_url" | "cost_class"> | undefined,
): boolean {
  if (!profile) return false;
  if (isLoopbackUrl(profile.base_url)) return false;
  return profile.cost_class !== "free";
}
