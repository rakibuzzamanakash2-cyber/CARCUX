"use client";

import { CalendarDays } from "lucide-react";
import { useEffect, useState } from "react";

const day = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Dhaka",
  weekday: "short",
  day: "numeric",
  month: "short",
  year: "numeric",
});
const time = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Dhaka",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** Dhaka date and time, ticking. Rendered on the client only, so it never mismatches. */
export function DhakaClock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    const tick = () => setNow(new Date());
    tick();
    const id = window.setInterval(tick, 15_000);
    return () => window.clearInterval(id);
  }, []);
  return (
    <div className="flex items-center gap-3 text-sm">
      <CalendarDays size={22} strokeWidth={1.6} aria-hidden="true" className="text-[#5fd38a]" />
      <span className="leading-tight tabular-nums" suppressHydrationWarning>
        <span className="block font-semibold text-white">{now ? day.format(now) : " "}</span>
        <span className="block text-night-muted">{now ? `${time.format(now)} Dhaka` : " "}</span>
      </span>
    </div>
  );
}
