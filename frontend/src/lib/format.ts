/** Display helpers shared by server and client components. */

/** CARCUX works in Bangladesh: all times are shown in Dhaka time (UTC+06:00, no DST). */
export const DHAKA_OFFSET = "+06:00";

const dateTime = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Dhaka",
});

export function formatDhaka(iso: string): string {
  return dateTime.format(new Date(iso));
}

/** The current Dhaka time as a value for <input type="datetime-local">. */
export function dhakaNowLocalInput(now = new Date()): string {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Dhaka",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(now)
      .map((p) => [p.type, p.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatCoords(lat: number, lon: number): string {
  return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}

/** What each integrity flag means, in words an analyst can act on. */
export const FLAG_INFO: Record<string, { label: string; meaning: string }> = {
  photo_reused: {
    label: "Photo reused",
    meaning:
      "A photo is identical or nearly identical to one in an earlier report. It may be recycled from another incident, or the same scene sent twice.",
  },
  impossible_travel: {
    label: "Impossible travel",
    meaning:
      "This worker's previous report was too far away to reach in the time between them (over 150 km/h). The GPS position or the time may be wrong.",
  },
  observed_in_future: {
    label: "Time in the future",
    meaning:
      "The reported time is later than when the server received it. The phone clock may be wrong.",
  },
  old_observation: {
    label: "Old observation",
    meaning:
      "The situation was seen more than 24 hours before the report arrived. It may no longer be current.",
  },
  submission_burst: {
    label: "Burst of submissions",
    meaning:
      "This worker sent many reports in a few minutes. Check that they are separate observations.",
  },
  poor_location_accuracy: {
    label: "Rough location",
    meaning: "The phone reported a weak GPS fix, so the true position may be far from the pin.",
  },
};

export function flagLabel(code: string): string {
  return FLAG_INFO[code]?.label ?? code.replace(/_/g, " ");
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: string): boolean {
  return UUID_RE.test(value);
}
