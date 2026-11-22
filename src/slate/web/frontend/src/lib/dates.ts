// Local calendar dates as ISO strings ("2026-11-21"). "Today" always comes from the
// server (agenda.today) so it follows the user's time zone setting, not the browser's.

const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

export function toDate(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

export function toIso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function addDays(iso: string, n: number): string {
  const d = toDate(iso);
  d.setUTCDate(d.getUTCDate() + n);
  return toIso(d);
}

export function diffDays(a: string, b: string): number {
  return Math.round((toDate(a).getTime() - toDate(b).getTime()) / 86_400_000);
}

export function weekday(iso: string): number {
  return toDate(iso).getUTCDay();
}

export function weekdayName(iso: string, short = false): string {
  const name = WEEKDAYS[weekday(iso)];
  return short ? name.slice(0, 3) : name;
}

export function monthName(iso: string, short = false): string {
  const name = MONTHS[toDate(iso).getUTCMonth()];
  return short ? name.slice(0, 3) : name;
}

export function dayOfMonth(iso: string): number {
  return toDate(iso).getUTCDate();
}

/** "Saturday, November 21" */
export function formatLong(iso: string): string {
  return `${weekdayName(iso)}, ${monthName(iso)} ${dayOfMonth(iso)}`;
}

/** "Tue, Nov 24" (with the year when it differs from today's). */
export function formatShort(iso: string, today?: string): string {
  const base = `${weekdayName(iso, true)}, ${monthName(iso, true)} ${dayOfMonth(iso)}`;
  if (today && iso.slice(0, 4) !== today.slice(0, 4)) return `${base}, ${iso.slice(0, 4)}`;
  return base;
}

/** Compact relative label for rows: Today, Tomorrow, Yesterday, Tue, Nov 30. */
export function formatDue(iso: string, today: string): string {
  const delta = diffDays(iso, today);
  if (delta === 0) return "Today";
  if (delta === 1) return "Tomorrow";
  if (delta === -1) return "Yesterday";
  if (delta > 1 && delta < 7) return weekdayName(iso, true);
  const base = `${monthName(iso, true)} ${dayOfMonth(iso)}`;
  return iso.slice(0, 4) === today.slice(0, 4) ? base : `${base}, ${iso.slice(0, 4)}`;
}

/** "17:30:00" -> "5:30pm", "09:00:00" -> "9am". */
export function formatTime(t: string | null | undefined): string {
  if (!t) return "";
  const [h, m] = t.split(":").map(Number);
  const suffix = h < 12 ? "am" : "pm";
  const hour = h % 12 === 0 ? 12 : h % 12;
  return m ? `${hour}:${String(m).padStart(2, "0")}${suffix}` : `${hour}${suffix}`;
}

export type DueTone = "overdue" | "today" | "soon" | "later";

export function dueTone(iso: string, today: string): DueTone {
  const delta = diffDays(iso, today);
  if (delta < 0) return "overdue";
  if (delta === 0) return "today";
  if (delta < 7) return "soon";
  return "later";
}

/** Quick picks used by the due menu and the phone swipe sheet. */
export function quickDates(today: string): { label: string; date: string; hint: string }[] {
  const tomorrow = addDays(today, 1);
  // The next Saturday after today; on a weekend that is next week's.
  const sat = addDays(today, (6 - weekday(today) + 7) % 7 || 7);
  const mon = addDays(today, (1 - weekday(today) + 7) % 7 || 7);
  return [
    { label: "Today", date: today, hint: weekdayName(today, true) },
    { label: "Tomorrow", date: tomorrow, hint: weekdayName(tomorrow, true) },
    {
      // On a Saturday or Sunday the next Saturday is a week out.
      label: weekday(today) === 0 || weekday(today) === 6 ? "Next weekend" : "This weekend",
      date: sat,
      hint: formatShort(sat, today),
    },
    { label: "Next week", date: mon, hint: formatShort(mon, today) },
  ];
}

/** Relative time for activity and comments: "just now", "5m", "3h", "Nov 20". */
export function formatRelative(timestamp: string, now: Date = new Date()): string {
  const then = new Date(timestamp);
  const secs = Math.round((now.getTime() - then.getTime()) / 1000);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86_400) return `${Math.floor(secs / 3600)}h ago`;
  if (secs < 7 * 86_400) return `${Math.floor(secs / 86_400)}d ago`;
  return then.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
