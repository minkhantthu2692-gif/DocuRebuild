import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Checkbox } from "@/components/ui/checkbox";
import { Radio } from "@/components/ui/radio";
import { Switch } from "@/components/ui/switch";

describe("form control primitives", () => {
  it("keeps checkbox semantics while rendering the themed indicator", () => {
    const onChange = vi.fn();
    render(
      <label>
        <Checkbox onChange={onChange} />
        Include source note
      </label>,
    );

    const checkbox = screen.getByRole("checkbox", { name: "Include source note" });
    expect(checkbox).not.toBeChecked();

    fireEvent.click(checkbox);

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("checkbox", { name: "Include source note" })).toBe(checkbox);
  });

  it("reports a mixed selection without losing the checkbox role", () => {
    render(
      <label>
        <Checkbox checked={false} indeterminate readOnly onChange={() => {}} />
        Select all pages
      </label>,
    );

    const checkbox = screen.getByRole("checkbox", {
      name: "Select all pages",
    }) as HTMLInputElement;
    expect(checkbox.indeterminate).toBe(true);
  });

  it("exposes a binary setting as a switch", () => {
    render(
      <label>
        <Switch defaultChecked />
        Grayscale
      </label>,
    );

    const toggle = screen.getByRole("switch", { name: "Grayscale" });
    expect(toggle).toBeChecked();
    expect(screen.queryByRole("checkbox")).toBeNull();

    fireEvent.click(toggle);
    expect(toggle).not.toBeChecked();
  });

  it("keeps radio groups as native radios", () => {
    render(
      <fieldset>
        <legend>Restore source</legend>
        <label>
          <Radio name="restore-source" value="current" defaultChecked /> Current document
        </label>
        <label>
          <Radio name="restore-source" value="revision" /> Latest revision
        </label>
      </fieldset>,
    );

    expect(screen.getByRole("radio", { name: "Current document" })).toBeChecked();
    fireEvent.click(screen.getByRole("radio", { name: "Latest revision" }));
    expect(screen.getByRole("radio", { name: "Latest revision" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Current document" })).not.toBeChecked();
  });
});
