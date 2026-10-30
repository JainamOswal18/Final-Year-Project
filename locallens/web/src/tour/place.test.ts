import { describe, expect, it } from "vitest";
import { placeCard } from "./place";

const card = { w: 400, h: 300 };

describe("placeCard", () => {
  it("sits in the middle when there is nothing to point at", () => {
    expect(placeCard(null, card, 1200, 800)).toEqual({ top: 250, left: 400, anchored: false });
  });
  it("prefers the side asked for when it fits", () => {
    const p = placeCard({ top: 100, left: 20, width: 200, height: 36 }, card, 1200, 800, "right");
    expect(p).toEqual({ top: 100, left: 234, anchored: true });
  });
  it("moves below when the preferred side has no room", () => {
    const p = placeCard({ top: 20, left: 900, width: 250, height: 40 }, card, 1200, 800, "right");
    expect(p.anchored).toBe(true);
    expect(p.top).toBe(74);
    expect(p.left + card.w).toBeLessThanOrEqual(1200 - 12);   // clamped inside the window
  });
  it("keeps the card clear of an element at the bottom edge", () => {
    const t = { top: 740, left: 20, width: 240, height: 36 };
    const p = placeCard(t, card, 1200, 800, "bottom");
    expect(p.anchored).toBe(true);
    const above = p.top + card.h <= t.top, beside = p.left >= t.left + t.width;
    expect(above || beside).toBe(true);                      // it does not cover what it points at
    expect(p.top + card.h).toBeLessThanOrEqual(800 - 12);
  });
  it("falls back to the middle on a screen too small for the card beside the element", () => {
    const p = placeCard({ top: 200, left: 20, width: 300, height: 400 }, { w: 340, h: 500 }, 360, 640, "right");
    expect(p.anchored).toBe(false);
  });
  it("never leaves the window", () => {
    for (const t of [{ top: 0, left: 0, width: 50, height: 20 }, { top: 780, left: 1190, width: 10, height: 20 }, { top: 400, left: 600, width: 100, height: 100 }]) {
      const p = placeCard(t, card, 1200, 800);
      expect(p.top).toBeGreaterThanOrEqual(12); expect(p.left).toBeGreaterThanOrEqual(12);
      expect(p.top + card.h).toBeLessThanOrEqual(800 - 12); expect(p.left + card.w).toBeLessThanOrEqual(1200 - 12);
    }
  });
});
