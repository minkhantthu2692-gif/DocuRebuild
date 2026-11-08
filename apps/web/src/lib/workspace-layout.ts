/**
 * Persisted workspace panel layout. Kept in localStorage because it is a device
 * preference, not project data.
 */
export interface WorkspaceLayout {
  sourceVisible: boolean;
  editorVisible: boolean;
  /** Share of the workspace width used by the source panel, 0.28–0.68. */
  split: number;
}

export const WORKSPACE_LAYOUT_KEY = "docurebuild.workspace-layout";

export const MIN_SPLIT = 0.28;
export const MAX_SPLIT = 0.68;

export const DEFAULT_WORKSPACE_LAYOUT: WorkspaceLayout = {
  sourceVisible: true,
  editorVisible: true,
  split: 0.46,
};

export function clampSplit(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_WORKSPACE_LAYOUT.split;
  return Math.min(MAX_SPLIT, Math.max(MIN_SPLIT, value));
}

/** Ensures at least one panel stays visible. */
export function normalizeLayout(layout: WorkspaceLayout): WorkspaceLayout {
  const sourceVisible = layout.sourceVisible;
  const editorVisible = layout.editorVisible;
  if (!sourceVisible && !editorVisible) {
    return { ...layout, sourceVisible: true };
  }
  return { ...layout, split: clampSplit(layout.split) };
}

export function readWorkspaceLayout(): WorkspaceLayout {
  try {
    const raw = localStorage.getItem(WORKSPACE_LAYOUT_KEY);
    if (!raw) return DEFAULT_WORKSPACE_LAYOUT;
    const parsed = JSON.parse(raw) as Partial<WorkspaceLayout>;
    return normalizeLayout({
      sourceVisible: parsed.sourceVisible ?? DEFAULT_WORKSPACE_LAYOUT.sourceVisible,
      editorVisible: parsed.editorVisible ?? DEFAULT_WORKSPACE_LAYOUT.editorVisible,
      split: parsed.split ?? DEFAULT_WORKSPACE_LAYOUT.split,
    });
  } catch {
    return DEFAULT_WORKSPACE_LAYOUT;
  }
}

export function writeWorkspaceLayout(layout: WorkspaceLayout): void {
  try {
    localStorage.setItem(WORKSPACE_LAYOUT_KEY, JSON.stringify(normalizeLayout(layout)));
  } catch {
    /* Storage may be unavailable; the in-memory layout still works. */
  }
}
