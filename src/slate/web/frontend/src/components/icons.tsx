import type { Priority, TaskStatus } from "../lib/api";

export const STATUSES: { value: TaskStatus; label: string }[] = [
  { value: "backlog", label: "Backlog" },
  { value: "todo", label: "Todo" },
  { value: "in_progress", label: "In progress" },
  { value: "done", label: "Done" },
  { value: "canceled", label: "Canceled" },
];

export const PRIORITIES: { value: Priority; label: string }[] = [
  { value: 0, label: "No priority" },
  { value: 1, label: "Urgent" },
  { value: 2, label: "High" },
  { value: 3, label: "Medium" },
  { value: 4, label: "Low" },
];

export const statusLabel = (s: TaskStatus) => STATUSES.find((x) => x.value === s)?.label ?? s;
export const priorityLabel = (p: number) => PRIORITIES.find((x) => x.value === p)?.label ?? "";

const STATUS_COLOR: Record<TaskStatus, string> = {
  backlog: "text-ink3",
  todo: "text-ink2",
  in_progress: "text-amber",
  done: "text-accent",
  canceled: "text-ink3",
};

/** Linear-style status circles: dashed, empty, half, check, x. */
export function StatusIcon({ status, size = 14 }: { status: TaskStatus; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 14 14",
    className: `shrink-0 ${STATUS_COLOR[status]}`,
    "aria-hidden": true,
  } as const;
  switch (status) {
    case "backlog":
      return (
        <svg {...common}>
          <circle
            cx="7"
            cy="7"
            r="5.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeDasharray="2 2.1"
          />
        </svg>
      );
    case "todo":
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      );
    case "in_progress":
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <path d="M7 3.5a3.5 3.5 0 0 1 0 7z" fill="currentColor" />
        </svg>
      );
    case "done":
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="6.25" fill="currentColor" />
          <path
            d="M4.4 7.2l1.8 1.8 3.5-3.7"
            fill="none"
            stroke="rgb(var(--panel))"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "canceled":
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="6.25" fill="currentColor" />
          <path
            d="M5 5l4 4M9 5l-4 4"
            stroke="rgb(var(--panel))"
            strokeWidth="1.4"
            strokeLinecap="round"
          />
        </svg>
      );
  }
}

/** Linear-style signal bars; urgent is a red exclamation box. */
export function PriorityIcon({ priority, size = 14 }: { priority: number; size?: number }) {
  if (priority === 1) {
    return (
      <svg width={size} height={size} viewBox="0 0 14 14" className="shrink-0 text-red" aria-hidden>
        <rect x="1" y="1" width="12" height="12" rx="3" fill="currentColor" />
        <path d="M7 3.8v4" stroke="rgb(var(--panel))" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="7" cy="10.2" r="0.95" fill="rgb(var(--panel))" />
      </svg>
    );
  }
  if (priority === 0) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 14 14"
        className="shrink-0 text-ink3"
        aria-hidden
      >
        <path
          d="M2.5 7h2M6 7h2M9.5 7h2"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  const lit = 5 - priority; // high 3, medium 2, low 1
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" className="shrink-0" aria-hidden>
      {[0, 1, 2].map((i) => (
        <rect
          key={i}
          x={2 + i * 3.7}
          y={9 - i * 3}
          width="2.6"
          height={3 + i * 3}
          rx="0.8"
          fill={i < lit ? "rgb(var(--ink2))" : "rgb(var(--line2))"}
        />
      ))}
    </svg>
  );
}

type IconProps = { className?: string; size?: number };

function Icon({ d, className = "", size = 16 }: IconProps & { d: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`shrink-0 ${className}`}
      aria-hidden
    >
      <path d={d} />
    </svg>
  );
}

export const IconToday = (p: IconProps) => (
  <Icon {...p} d="M3 4.5h10v8.5H3zM3 7h10M5.5 2.5v2M10.5 2.5v2M8 9.2v1.6" />
);
export const IconUpcoming = (p: IconProps) => (
  <Icon
    {...p}
    d="M3 4.5h10v8.5H3zM3 7h10M5.5 2.5v2M10.5 2.5v2M5.5 9.5h1M7.5 9.5h1M9.5 9.5h1M5.5 11.3h1"
  />
);
export const IconInbox = (p: IconProps) => (
  <Icon {...p} d="M2.5 9l1.8-5.5h7.4L13.5 9v3.5h-11zM2.5 9h3.2l.8 1.5h3l.8-1.5h3.2" />
);
export const IconAll = (p: IconProps) => (
  <Icon {...p} d="M5.5 4.5h8M5.5 8h8M5.5 11.5h8M2.5 4.5h.5M2.5 8h.5M2.5 11.5h.5" />
);
export const IconProjects = (p: IconProps) => (
  <Icon {...p} d="M2.5 4.5l1-1.5h3l1 1.5h6v8h-11zM2.5 6.5h11" />
);
export const IconPlus = (p: IconProps) => <Icon {...p} d="M8 3v10M3 8h10" />;
export const IconSearch = (p: IconProps) => (
  <Icon {...p} d="M7 12A5 5 0 1 0 7 2a5 5 0 0 0 0 10zM10.6 10.6L14 14" />
);
export const IconClose = (p: IconProps) => <Icon {...p} d="M4 4l8 8M12 4l-8 8" />;
export const IconSun = (p: IconProps) => (
  <Icon
    {...p}
    d="M8 10.8a2.8 2.8 0 1 0 0-5.6 2.8 2.8 0 0 0 0 5.6zM8 1.5v1.3M8 13.2v1.3M1.5 8h1.3M13.2 8h1.3M3.4 3.4l.9.9M11.7 11.7l.9.9M3.4 12.6l.9-.9M11.7 4.3l.9-.9"
  />
);
export const IconMoon = (p: IconProps) => (
  <Icon {...p} d="M13 9.5A5.5 5.5 0 0 1 6.5 3a5.5 5.5 0 1 0 6.5 6.5z" />
);
export const IconRepeat = (p: IconProps) => (
  <Icon
    {...p}
    d="M3 7V6a2 2 0 0 1 2-2h7.5M10.5 2l2 2-2 2M13 9v1a2 2 0 0 1-2 2H3.5M5.5 14l-2-2 2-2"
  />
);
export const IconCalendar = (p: IconProps) => (
  <Icon {...p} d="M3 4.5h10v8.5H3zM3 7h10M5.5 2.5v2M10.5 2.5v2" />
);
export const IconComment = (p: IconProps) => <Icon {...p} d="M3 3.5h10v7H7l-3 2.5v-2.5H3z" />;
export const IconSubtasks = (p: IconProps) => (
  <Icon {...p} d="M4 3v7.5h3M4 6.5h3M9 5h4.5M9 10.5h4.5" />
);
export const IconBoard = (p: IconProps) => (
  <Icon {...p} d="M2.5 3h3v10h-3zM6.5 3h3v6.5h-3zM10.5 3h3v8h-3z" />
);
export const IconList = (p: IconProps) => <Icon {...p} d="M2.5 4h11M2.5 8h11M2.5 12h11" />;
export const IconSettings = (p: IconProps) => (
  <Icon
    {...p}
    d="M8 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM8 1.8v1.6M8 12.6v1.6M3.6 3.6l1.1 1.1M11.3 11.3l1.1 1.1M1.8 8h1.6M12.6 8h1.6M3.6 12.4l1.1-1.1M11.3 4.7l1.1-1.1"
  />
);
export const IconChevron = (p: IconProps) => <Icon {...p} d="M6 4l4 4-4 4" />;
export const IconBack = (p: IconProps) => <Icon {...p} d="M10 3.5L5.5 8l4.5 4.5" />;
export const IconTag = (p: IconProps) => (
  <Icon {...p} d="M2.5 2.5h5.3l6 6-5.3 5.3-6-6zM5.3 5.3h.01" />
);
export const IconTrash = (p: IconProps) => (
  <Icon {...p} d="M3 4.5h10M6.5 4.5V3h3v1.5M4.3 4.5l.6 8.5h6.2l.6-8.5" />
);
export const IconSignOut = (p: IconProps) => (
  <Icon {...p} d="M6.5 3H3v10h3.5M10 5l3 3-3 3M13 8H6.5" />
);
export const IconFlag = (p: IconProps) => <Icon {...p} d="M3.5 14V2.5M3.5 3h8l-1.5 3 1.5 3h-8" />;
export const IconCheck = (p: IconProps) => <Icon {...p} d="M3.5 8.5l3 3 6-7" />;

export function Dot({ color, size = 8 }: { color: string; size?: number }) {
  return (
    <span
      className="inline-block shrink-0 rounded-full"
      style={{ width: size, height: size, background: color }}
      aria-hidden
    />
  );
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="kbd">{children}</kbd>;
}
