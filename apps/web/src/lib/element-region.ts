import type { ImageFrame } from "./layout-overlay";

/** A rectangle in source-image pixels, exactly as stored by the backend. */
export interface SourceRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface DisplayPoint {
  x: number;
  y: number;
}

/** Smallest selectable side in source pixels, mirroring the backend limit. */
export const MIN_REGION_SIDE = 8;

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}

/**
 * Convert a marquee drag on the rendered page into a source-pixel rectangle.
 * Both points use the viewer content coordinate space, which is also the space
 * of `ImageFrame`. Incomplete geometry returns null instead of guessing.
 */
export function selectionToSourceRect(
  start: DisplayPoint,
  end: DisplayPoint,
  frame: ImageFrame | null,
): SourceRect | null {
  if (!frame) return null;
  if (
    ![frame.left, frame.top, frame.width, frame.height].every(Number.isFinite) ||
    frame.width <= 0 ||
    frame.height <= 0 ||
    frame.naturalWidth <= 0 ||
    frame.naturalHeight <= 0
  ) {
    return null;
  }

  const scaleX = frame.naturalWidth / frame.width;
  const scaleY = frame.naturalHeight / frame.height;

  const clampX = (value: number) => clamp(value, frame.left, frame.left + frame.width);
  const clampY = (value: number) => clamp(value, frame.top, frame.top + frame.height);

  const left = Math.round((clampX(Math.min(start.x, end.x)) - frame.left) * scaleX);
  const top = Math.round((clampY(Math.min(start.y, end.y)) - frame.top) * scaleY);
  const right = Math.round((clampX(Math.max(start.x, end.x)) - frame.left) * scaleX);
  const bottom = Math.round((clampY(Math.max(start.y, end.y)) - frame.top) * scaleY);

  const width = clamp(right - left, 0, frame.naturalWidth);
  const height = clamp(bottom - top, 0, frame.naturalHeight);
  if (width < MIN_REGION_SIDE || height < MIN_REGION_SIDE) return null;

  return {
    x: clamp(left, 0, Math.max(0, frame.naturalWidth - width)),
    y: clamp(top, 0, Math.max(0, frame.naturalHeight - height)),
    width,
    height,
  };
}

/** Movement between two points, used for the visible marquee rectangle. */
export function displayRect(
  start: DisplayPoint,
  end: DisplayPoint,
): { left: number; top: number; width: number; height: number } {
  return {
    left: Math.min(start.x, end.x),
    top: Math.min(start.y, end.y),
    width: Math.abs(end.x - start.x),
    height: Math.abs(end.y - start.y),
  };
}
