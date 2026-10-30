import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { HowTo } from "./help";

describe("HowTo", () => {
  beforeEach(() => localStorage.clear());

  it("starts open for a first-time reader and remembers when they close it", async () => {
    const { unmount } = render(<HowTo id="t1" title="How to"><p>Details</p></HowTo>);
    const details = document.querySelector("details")!;
    expect(details.open).toBe(true);
    await userEvent.click(screen.getByText("How to"));
    expect(localStorage.getItem("ll-help-t1")).toBe("closed");
    unmount();
    render(<HowTo id="t1" title="How to"><p>Details</p></HowTo>);
    expect(document.querySelector("details")!.open).toBe(false);
  });

  it("can start closed when the page already has content", () => {
    render(<HowTo id="t2" title="Closed first" defaultOpen={false}><p>Details</p></HowTo>);
    expect(document.querySelector("details")!.open).toBe(false);
  });
});
