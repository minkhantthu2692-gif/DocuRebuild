import { describe, expect, it } from "vitest";

import {
  ACCEPTED_IMAGE_EXTENSIONS,
  isSupportedImageFile,
  partitionImageFiles,
} from "@/lib/image-files";

function file(name: string, size = 10): File {
  return new File([new Uint8Array(size)], name, { type: "application/octet-stream" });
}

describe("image file pre-validation", () => {
  it("accepts every documented image extension case-insensitively", () => {
    for (const extension of ACCEPTED_IMAGE_EXTENSIONS) {
      expect(isSupportedImageFile(file(`page${extension.toUpperCase()}`))).toBe(true);
    }
  });

  it("rejects unsupported types and oversized files separately", () => {
    const result = partitionImageFiles(
      [file("scan.png", 5), file("notes.txt", 5), file("huge.tiff", 500)],
      100,
    );

    expect(result.accepted.map((item) => item.name)).toEqual(["scan.png"]);
    expect(result.rejected.map((item) => [item.file.name, item.reason])).toEqual([
      ["notes.txt", "unsupported"],
      ["huge.tiff", "too_large"],
    ]);
  });

  it("does not enforce a size limit when the backend limit is unknown", () => {
    const result = partitionImageFiles([file("huge.tiff", 10_000)], null);
    expect(result.accepted).toHaveLength(1);
    expect(result.rejected).toHaveLength(0);
  });
});
