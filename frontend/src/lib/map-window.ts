/** How far back the situation map looks: today (since midnight in Dhaka), or 3 or 7 days. */
export const MAP_WINDOWS = { today: "Today", "3d": "3 days", "7d": "7 days" } as const;
export type MapWindow = keyof typeof MAP_WINDOWS;
export const DEFAULT_MAP_WINDOW: MapWindow = "3d";

export function parseMapWindow(value: string | undefined): MapWindow {
  return value && value in MAP_WINDOWS ? (value as MapWindow) : DEFAULT_MAP_WINDOW;
}

/** The start of the window as an ISO time. Bangladesh is UTC+6 with no daylight saving. */
export function mapWindowStart(window: MapWindow, now: number = Date.now()): string {
  if (window === "today") {
    const dhaka = new Date(now + 6 * 3600 * 1000);
    dhaka.setUTCHours(0, 0, 0, 0);
    return new Date(dhaka.getTime() - 6 * 3600 * 1000).toISOString();
  }
  const days = window === "7d" ? 7 : 3;
  return new Date(now - days * 24 * 3600 * 1000).toISOString();
}
