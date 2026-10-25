// @vitest-environment jsdom
/** Connection configuration (Phase 17): standalone vs connect-to-server, with a test + save. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

const H = vi.hoisted(() => ({ getApiBase: vi.fn(() => "http://localhost:8000"), setApiBase: vi.fn() }));
vi.mock("../../lib/api", () => H);

import { ConnectionSettings } from "./ConnectionSettings";

afterEach(cleanup);

describe("ConnectionSettings", () => {
  it("defaults to standalone and reveals a URL field for server mode", () => {
    render(<ConnectionSettings />);
    expect(screen.getByText(/http:\/\/localhost:8000/)).toBeTruthy();
    // switch to "Connect to a server" → a URL input appears
    fireEvent.click(screen.getByText(/Connect to a server/));
    expect(screen.getByLabelText("Server URL")).toBeTruthy();
    // Save is disabled until a URL is entered
    const save = screen.getByText("Save & reconnect") as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Server URL"), { target: { value: "https://server.local:8000" } });
    expect((screen.getByText("Save & reconnect") as HTMLButtonElement).disabled).toBe(false);
  });
});
