import type { OcrBlock, OcrBlockKind } from "@docurebuild/shared-types";

/** Rendered image box in the coordinates of the viewer content area. */
export interface ImageFrame {
  left: number;
  top: number;
  width: number;
  height: number;
  naturalWidth: number;
  naturalHeight: number;
}

/** A block box in rendered-image pixels, relative to the image origin. */
export interface LayoutBox {
  id: string;
  kind: OcrBlockKind;
  left: number;
  top: number;
  width: number;
  height: number;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}

function isUsable(value: number | null): value is number {
  return value !== null && Number.isFinite(value);
}

/**
 * Convert OCR pixel coordinates into positions relative to the rendered image.
 * Both the image box and the source coordinates are required; incomplete
 * geometry is skipped rather than drawn in the wrong place.
 */
export function layoutBoxes(blocks: OcrBlock[], frame: ImageFrame): LayoutBox[] {
  if (
    !Number.isFinite(frame.width) ||
    !Number.isFinite(frame.height) ||
    !Number.isFinite(frame.naturalWidth) ||
    !Number.isFinite(frame.naturalHeight) ||
    frame.width <= 0 ||
    frame.height <= 0 ||
    frame.naturalWidth <= 0 ||
    frame.naturalHeight <= 0
  ) {
    return [];
  }

  const scaleX = frame.width / frame.naturalWidth;
  const scaleY = frame.height / frame.naturalHeight;

  return blocks.flatMap((block) => {
    if (!isUsable(block.x) || !isUsable(block.y)) return [];
    if (!isUsable(block.width) || !isUsable(block.height)) return [];
    if (block.width <= 0 || block.height <= 0) return [];

    const left = clamp(block.x, 0, frame.naturalWidth);
    const top = clamp(block.y, 0, frame.naturalHeight);
    const right = clamp(block.x + block.width, 0, frame.naturalWidth);
    const bottom = clamp(block.y + block.height, 0, frame.naturalHeight);
    if (right <= left || bottom <= top) return [];

    return [
      {
        id: block.id,
        kind: block.kind,
        left: left * scaleX,
        top: top * scaleY,
        width: (right - left) * scaleX,
        height: (bottom - top) * scaleY,
      },
    ];
  });
}

/**
 * Convert a source-pixel rectangle into positions relative to the rendered
 * image. Out-of-page parts are clipped, and unusable geometry is skipped.
 */
export function layoutRect(
  rect: { x: number; y: number; width: number; height: number },
  frame: ImageFrame,
): { left: number; top: number; width: number; height: number } | null {
  if (
    !Number.isFinite(frame.width) ||
    !Number.isFinite(frame.height) ||
    !Number.isFinite(frame.naturalWidth) ||
    !Number.isFinite(frame.naturalHeight) ||
    frame.width <= 0 ||
    frame.height <= 0 ||
    frame.naturalWidth <= 0 ||
    frame.naturalHeight <= 0
  ) {
    return null;
  }
  if (![rect.x, rect.y, rect.width, rect.height].every(Number.isFinite)) return null;

  const left = clamp(rect.x, 0, frame.naturalWidth);
  const top = clamp(rect.y, 0, frame.naturalHeight);
  const right = clamp(rect.x + rect.width, 0, frame.naturalWidth);
  const bottom = clamp(rect.y + rect.height, 0, frame.naturalHeight);
  if (right <= left || bottom <= top) return null;

  const scaleX = frame.width / frame.naturalWidth;
  const scaleY = frame.height / frame.naturalHeight;
  return {
    left: left * scaleX,
    top: top * scaleY,
    width: (right - left) * scaleX,
    height: (bottom - top) * scaleY,
  };
}

/**
 * Fit the natural image inside a measured element box, mirroring the
 * `object-contain` rendering used by the viewer.
 */
export function containFrame(
  base: { left: number; top: number; width: number; height: number },
  naturalWidth: number,
  naturalHeight: number,
): ImageFrame | null {
  if (
    ![base.left, base.top, base.width, base.height, naturalWidth, naturalHeight].every(
      Number.isFinite,
    ) ||
    base.width <= 0 ||
    base.height <= 0 ||
    naturalWidth <= 0 ||
    naturalHeight <= 0
  ) {
    return null;
  }

  const ratio = Math.min(base.width / naturalWidth, base.height / naturalHeight);
  const width = naturalWidth * ratio;
  const height = naturalHeight * ratio;

  return {
    left: base.left + (base.width - width) / 2,
    top: base.top + (base.height - height) / 2,
    width,
    height,
    naturalWidth,
    naturalHeight,
  };
}
