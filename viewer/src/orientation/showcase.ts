export const ORIENTATION_SHOWCASE_EVENT = "arch-viz-orientation-showcase";

export type OrientationShowcaseDetail = {
  stopId: string | null;
};

export function announceOrientationShowcase(stopId: string | null): void {
  window.dispatchEvent(new CustomEvent<OrientationShowcaseDetail>(ORIENTATION_SHOWCASE_EVENT, {
    detail: { stopId },
  }));
}
