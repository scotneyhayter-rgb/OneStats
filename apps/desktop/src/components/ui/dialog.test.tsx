// @vitest-environment jsdom
/** Regression: typing in a field inside a Modal must NOT lose focus. The focus-management effect
 *  must depend only on `open` — not on an inline `onClose` that the parent recreates every render,
 *  which would re-run the effect on each keystroke and yank focus onto the dialog container. */
import { afterEach, describe, expect, it } from "vitest";
import { useState } from "react";
import { cleanup, fireEvent, render } from "@testing-library/react";
import { Modal } from "./dialog";
import { Input } from "./input";

afterEach(cleanup);

function Harness() {
  const [v, setV] = useState("");
  // onClose is a fresh arrow on every render — the exact pattern DangerZone used that triggered the bug.
  return (
    <Modal open title="Delete workspace?" onClose={() => setV((x) => x)}>
      <Input aria-label="confirm" value={v} onChange={(e) => setV(e.target.value)} />
    </Modal>
  );
}

describe("Modal focus management", () => {
  it("keeps focus in an input while typing (effect depends only on open)", () => {
    const { getByLabelText } = render(<Harness />);
    const input = getByLabelText("confirm") as HTMLInputElement;

    input.focus();
    expect(document.activeElement).toBe(input);

    // Type several characters; each change re-renders the parent (new onClose identity). Focus must stay.
    for (const ch of ["s", "a", "n", "d"]) {
      fireEvent.change(input, { target: { value: input.value + ch } });
      expect(document.activeElement).toBe(input); // not stolen back to the dialog container
    }
    expect(input.value).toBe("sand");
  });

  it("does not steal focus from an element already focused inside the dialog on open", () => {
    const { getByLabelText } = render(
      <Modal open title="x" onClose={() => {}}>
        <Input aria-label="auto" autoFocus />
      </Modal>,
    );
    // autoFocus put focus on the input; the open effect must not pull it onto the dialog wrapper.
    expect(document.activeElement).toBe(getByLabelText("auto"));
  });
});
