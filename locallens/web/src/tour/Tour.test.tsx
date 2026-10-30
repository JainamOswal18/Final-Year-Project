import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  prefs: vi.fn(),
  setTour: vi.fn(),
  demoDataset: vi.fn(),
}));
vi.mock("../api", () => ({ api }));
vi.mock("../auth", () => ({
  useAuth: () => ({ user: { id: 1, username: "a", role: "user" } }),
  useDatasets: () => ({ list: [], loading: false, reload: vi.fn().mockResolvedValue(undefined) }),
}));

import { ToastProvider } from "../ui";
import { TourProvider, useTour } from "./Tour";

const Where = () => <output data-testid="where">{useLocation().pathname}</output>;
const Again = () => <button onClick={useTour().start}>Take the tour</button>;

function app() {
  return render(
    <MemoryRouter initialEntries={["/datasets"]}>
      <ToastProvider>
        <TourProvider>
          <Routes><Route path="*" element={<><Where /><Again /><button data-tour="new-dataset">New dataset</button><button data-tour="demo">Demo</button></>} /></Routes>
        </TourProvider>
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe("first-visit tour", () => {
  beforeEach(() => {
    api.prefs.mockReset().mockResolvedValue({ tour_done: false });
    api.setTour.mockReset().mockResolvedValue({ tour_done: true });
    api.demoDataset.mockReset().mockResolvedValue({ id: "demo1" });
  });

  it("opens by itself for someone who has not seen it, and walks forward and back", async () => {
    app();
    expect(await screen.findByRole("dialog", { name: "Welcome to LocalLens" })).toBeInTheDocument();
    expect(screen.getByText(/Step 1 of 12/)).toBeInTheDocument();      // a non-admin has no administration step
    await userEvent.click(screen.getByRole("button", { name: "Start the tour" }));
    expect(screen.getByRole("dialog", { name: "How it works, in four steps" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByRole("dialog", { name: "Welcome to LocalLens" })).toBeInTheDocument();
  });

  it("does not open for someone who has finished it", async () => {
    api.prefs.mockResolvedValue({ tour_done: true });
    app();
    await waitFor(() => expect(api.prefs).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("remembers a skip (button or Escape) on the server", async () => {
    app();
    await screen.findByRole("dialog");
    await userEvent.click(screen.getByRole("button", { name: "Skip tour" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(api.setTour).toHaveBeenCalledWith(true);
    await userEvent.click(screen.getByRole("button", { name: "Take the tour" }));   // can be replayed
    await screen.findByRole("dialog");
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(api.setTour).toHaveBeenCalledTimes(2);
  });

  it("moves with the arrow keys", async () => {
    app();
    await screen.findByRole("dialog");
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("dialog", { name: "How it works, in four steps" })).toBeInTheDocument();
    await userEvent.keyboard("{ArrowLeft}");
    expect(screen.getByRole("dialog", { name: "Welcome to LocalLens" })).toBeInTheDocument();
  });

  it("ends by offering the demo, which opens it and finishes the tour", async () => {
    app();
    await screen.findByRole("dialog");
    for (let i = 0; i < 11; i++) await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("dialog", { name: "You are ready" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Open the demo" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(api.demoDataset).toHaveBeenCalled();
    expect(screen.getByTestId("where")).toHaveTextContent("/d/demo1/ask");
    expect(api.setTour).toHaveBeenCalledWith(true);
  });

  it("lights up the element a step points at", async () => {
    // jsdom has no layout, so give every element a size; an element with no size counts as hidden and is not lit
    const spy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ top: 100, left: 50, width: 120, height: 36, right: 170, bottom: 136, x: 50, y: 100, toJSON: () => ({}) });
    app();
    await screen.findByRole("dialog");
    for (let i = 0; i < 3; i++) await userEvent.keyboard("{ArrowRight}");        // datasets, upload
    expect(screen.getByRole("dialog", { name: "Add your own data" })).toBeInTheDocument();
    await waitFor(() => expect(document.querySelector(".tour-spot")).not.toBeNull());
    spy.mockRestore();
  });

  it("shows the middle card, with no spotlight, when the element is not on the page", async () => {
    app();
    await screen.findByRole("dialog");
    for (let i = 0; i < 5; i++) await userEvent.keyboard("{ArrowRight}");        // columns: its sidebar link is not rendered here
    expect(screen.getByRole("dialog", { name: /^Columns/ })).toHaveClass("mid");
    expect(document.querySelector(".tour-spot")).toBeNull();
  });
});
