"use client";

import { useEffect, useState } from "react";

const fmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Dhaka",
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** Dhaka time, ticking each minute. Rendered on the client only, so it never mismatches. */
export function DhakaClock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    const tick = () => setNow(new Date());
    tick();
    const id = window.setInterval(tick, 15_000);
    return () => window.clearInterval(id);
  }, []);
  return (
    <time className="text-sm text-muted tabular-nums" suppressHydrationWarning>
      {now ? `${fmt.format(now)} Dhaka` : " "}
    </time>
  );
}
