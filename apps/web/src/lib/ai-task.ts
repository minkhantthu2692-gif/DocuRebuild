import type { AiUsageTask } from "@docurebuild/shared-types";

/**
 * Tasks this build gives a specific label to. The backend may still return a
 * task name from an older or newer build, so this list must never be treated as
 * a closed set when reading usage rows.
 */
export const AI_TASKS: readonly AiUsageTask[] = [
  "ocr_cleanup",
  "region_proposals",
  "equation_transcription",
  "table_structure",
];

export function isKnownAiTask(value: string): value is AiUsageTask {
  return (AI_TASKS as readonly string[]).includes(value);
}

/**
 * Translation key for a task name stored in the local ledger.
 *
 * Unknown names get a generic label instead of a raw key, so usage rows from
 * another build stay readable rather than breaking the view.
 */
export function aiTaskLabelKey(value: string): string {
  return isKnownAiTask(value) ? `ai.tasks.${value}` : "ai.history.unknownTask";
}
