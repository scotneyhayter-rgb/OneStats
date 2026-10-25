// @vitest-environment jsdom
/**
 * The official-total bar should let a scorer CONFIRM the total the scorecard already calculates in
 * one click (no re-typing total/wickets/reason), while still allowing a different authoritative
 * total for incomplete/amended cards. Guards the reduced-duplication behaviour the user asked for.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TotalsBar } from "./ScorecardEditor";
import type { Innings, InningsTotals } from "../../lib/api";

const innings = (o: Partial<Innings> = {}): Innings =>
  ({ official_total: null, official_wickets: null, ...o } as Innings);

const totals = (o: Partial<InningsTotals> = {}): InningsTotals =>
  ({ extras_total: 10, batting_runs: 140, derived_total: 150, derived_wickets: 10, ...o } as InningsTotals);

afterEach(cleanup);

describe("official total — confirm vs override", () => {
  it("confirms the calculated total in one click (adopts total + wickets, no typing)", async () => {
    const onOfficial = vi.fn();
    const user = userEvent.setup();
    render(<TotalsBar totals={totals()} innings={innings()} canManage onOfficial={onOfficial} />);
    await user.click(screen.getByRole("button", { name: /Confirm total 150\/10/i }));
    expect(onOfficial).toHaveBeenCalledWith(150, 10, "Confirmed from scorecard");
  });

  it("shows a confirmed state (no confirm button) once the official matches the calculated total", () => {
    render(<TotalsBar totals={totals()} innings={innings({ official_total: 150, official_wickets: 10 })} canManage onOfficial={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Confirm total/i })).toBeNull();
    expect(screen.getByText(/Confirmed from scorecard/i)).toBeTruthy();
  });

  it("still allows a different authoritative total for an incomplete/amended card", async () => {
    const onOfficial = vi.fn();
    const user = userEvent.setup();
    render(<TotalsBar totals={totals()} innings={innings()} canManage onOfficial={onOfficial} />);
    await user.click(screen.getByRole("button", { name: /Different total/i }));
    const [totalInput, wktsInput] = screen.getAllByRole("textbox");
    await user.clear(totalInput); await user.type(totalInput, "162");
    await user.clear(wktsInput); await user.type(wktsInput, "8");
    await user.click(screen.getByRole("button", { name: /Save official/i }));
    expect(onOfficial).toHaveBeenCalledWith(162, 8, expect.any(String));
  });
});
