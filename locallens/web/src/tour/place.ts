/** Where the tour card goes next to the highlighted element. Pure, so it can be tested without a browser. */
export type Place = "right" | "left" | "bottom" | "top";
export interface Box { top: number; left: number; width: number; height: number }
export interface Placement { top: number; left: number; anchored: boolean }

const GAP = 14;
const MARGIN = 12;

export function placeCard(target: Box | null, card: { w: number; h: number }, vw: number, vh: number, prefer: Place = "right"): Placement {
  const middle = { top: Math.max(MARGIN, (vh - card.h) / 2), left: Math.max(MARGIN, (vw - card.w) / 2), anchored: false };
  if (!target) return middle;
  const clampX = (x: number) => Math.min(Math.max(x, MARGIN), vw - card.w - MARGIN);
  const clampY = (y: number) => Math.min(Math.max(y, MARGIN), vh - card.h - MARGIN);
  const fits = (t: number, l: number) => t >= MARGIN && l >= MARGIN && t + card.h <= vh - MARGIN && l + card.w <= vw - MARGIN;
  const options: Record<Place, [number, number]> = {
    right: [clampY(target.top), target.left + target.width + GAP],
    left: [clampY(target.top), target.left - card.w - GAP],
    bottom: [target.top + target.height + GAP, clampX(target.left)],
    top: [target.top - card.h - GAP, clampX(target.left)],
  };
  for (const p of [prefer, "bottom", "right", "top", "left"] as Place[]) {
    const [top, left] = options[p];
    if (fits(top, left)) return { top, left, anchored: true };
  }
  return middle; // no room next to it (small screens): the card sits in the middle and the element is still lit
}
