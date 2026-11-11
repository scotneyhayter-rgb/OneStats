// @vitest-environment jsdom
/** App-wide toast system: useToast shows a message through the provider, and it can be dismissed. */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ToastProvider, useToast } from "./toast";

function Trigger() {
  const toast = useToast();
  return <button type="button" onClick={() => toast.success("Report saved.")}>fire</button>;
}

afterEach(cleanup);

describe("toast", () => {
  it("shows a toast on demand and dismisses it", () => {
    render(<ToastProvider><Trigger /></ToastProvider>);
    expect(screen.queryByText("Report saved.")).toBeNull();        // nothing until fired
    fireEvent.click(screen.getByText("fire"));
    expect(screen.getByText("Report saved.")).toBeTruthy();         // appears
    fireEvent.click(screen.getByLabelText("Dismiss"));
    expect(screen.queryByText("Report saved.")).toBeNull();         // gone after dismiss
  });

  it("is a no-op outside a provider (never throws)", () => {
    render(<Trigger />);
    expect(() => fireEvent.click(screen.getByText("fire"))).not.toThrow();
  });
});
