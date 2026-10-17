import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { Callout, ChipsInput, Seg } from "./ui";

function Harness({ start = [] as string[] }) {
  const [v, setV] = useState(start);
  return <><ChipsInput label="Synonyms" values={v} onChange={setV} /><output>{v.join("|")}</output></>;
}

describe("ChipsInput", () => {
  it("adds a chip on Enter and on comma, without duplicates", async () => {
    render(<Harness />);
    const box = screen.getByLabelText("Synonyms");
    await userEvent.type(box, "revenue{Enter}sales, revenue,");
    expect(document.querySelector("output")?.textContent).toBe("revenue|sales");
  });
  it("removes the last chip with Backspace and a chip with its x button", async () => {
    render(<Harness start={["a", "b", "c"]} />);
    await userEvent.type(screen.getByLabelText("Synonyms"), "{Backspace}");
    expect(document.querySelector("output")?.textContent).toBe("a|b");
    await userEvent.click(screen.getByLabelText("Remove a"));
    expect(document.querySelector("output")?.textContent).toBe("b");
  });
});

describe("Seg", () => {
  it("marks the chosen option and reports changes", async () => {
    const seen: string[] = [];
    render(<Seg label="Format" value="number" options={[{ value: "number", label: "Number" }, { value: "percent", label: "Percent" }]} onChange={(v) => seen.push(v)} />);
    expect(screen.getByRole("button", { name: "Number" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "Percent" }));
    expect(seen).toEqual(["percent"]);
  });
});

describe("Callout", () => {
  it("announces errors", () => {
    render(<Callout kind="bad">Something broke</Callout>);
    expect(screen.getByRole("alert")).toHaveTextContent("Something broke");
  });
});
