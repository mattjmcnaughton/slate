import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useIsPhone } from "../hooks/useMedia";
import { useTaskActions } from "../lib/actions";
import { formatDue, formatTime, quickDates } from "../lib/dates";
import { findTask, useCreateLabel, useLookups, useParse, useToday } from "../lib/queries";
import { type MenuState, useUI } from "../stores/ui";
import {
  Dot,
  IconCalendar,
  IconCheck,
  IconClose,
  IconInbox,
  IconPlus,
  IconRepeat,
  PRIORITIES,
  PriorityIcon,
  STATUSES,
  StatusIcon,
} from "./icons";

export interface Item {
  key: string;
  label: React.ReactNode;
  icon?: React.ReactNode;
  hint?: React.ReactNode;
  active?: boolean;
  /** Keep the menu open after choosing (multi-select). */
  keepOpen?: boolean;
  onSelect: () => void;
}

const TITLES: Record<MenuState["kind"], string> = {
  status: "Status",
  priority: "Priority",
  labels: "Labels",
  due: "Due date",
  project: "Move to",
};

export function MenuHost() {
  const menu = useUI((s) => s.menu);
  if (!menu) return null;
  return <Menu key={`${menu.kind}:${menu.taskIds.join(",")}`} menu={menu} />;
}

function Menu({ menu }: { menu: MenuState }) {
  const phone = useIsPhone();
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const close = () => useUI.getState().closeMenu();

  // Open at the anchor, else under the selected row; flip up when there is no room.
  useLayoutEffect(() => {
    if (phone || !ref.current) return;
    let x = menu.anchor?.x;
    let y = menu.anchor?.y;
    let rowTop = y;
    if (x === undefined || y === undefined) {
      const row = document.querySelector(`[data-task-id="${menu.taskIds[0]}"]`);
      const r = row?.getBoundingClientRect();
      x = r ? r.left + 96 : window.innerWidth / 2 - 140;
      y = r ? r.bottom + 4 : window.innerHeight / 3;
      rowTop = r ? r.top - 4 : y;
    }
    const { width, height } = ref.current.getBoundingClientRect();
    const left = Math.max(8, Math.min(x, window.innerWidth - width - 8));
    const top = y + height > window.innerHeight - 8 ? Math.max(8, (rowTop ?? y) - height) : y;
    setPos({ left, top });
  }, [menu, phone]);

  const body = (() => {
    switch (menu.kind) {
      case "status":
        return <StatusMenu ids={menu.taskIds} />;
      case "priority":
        return <PriorityMenu ids={menu.taskIds} />;
      case "labels":
        return <LabelsMenu ids={menu.taskIds} />;
      case "due":
        return <DueMenu ids={menu.taskIds} />;
      case "project":
        return <ProjectMenu ids={menu.taskIds} />;
    }
  })();

  if (phone) {
    return (
      <div className="fixed inset-0 z-50 flex items-end bg-ink/25">
        <button
          type="button"
          aria-label="Close"
          className="absolute inset-0 cursor-default"
          onClick={close}
        />
        <div
          ref={ref}
          role="dialog"
          aria-label={TITLES[menu.kind]}
          className="anim-sheet relative max-h-[80vh] w-full overflow-y-auto rounded-t-2xl bg-raise pb-[max(1rem,env(safe-area-inset-bottom))] shadow-[var(--shadow)]"
        >
          <div className="mx-auto mt-2 h-1 w-9 rounded-full bg-line2" />
          <div className="flex items-center justify-between px-4 pb-1 pt-3">
            <span className="text-[15px] font-semibold">{TITLES[menu.kind]}</span>
            <button type="button" onClick={close} className="p-1 text-ink3" aria-label="Close">
              <IconClose />
            </button>
          </div>
          {body}
        </div>
      </div>
    );
  }

  return (
    <>
      <button
        type="button"
        aria-label="Close menu"
        tabIndex={-1}
        className="fixed inset-0 z-40 cursor-default"
        onClick={close}
      />
      <div
        ref={ref}
        role="dialog"
        aria-label={TITLES[menu.kind]}
        className="popover anim-rise fixed z-50 w-[272px] overflow-hidden py-1"
        style={pos ? { left: pos.left, top: pos.top } : { left: -9999, top: 0 }}
      >
        {body}
      </div>
    </>
  );
}

/**
 * A keyboard list: arrows move, Enter chooses, digits 1-9 choose directly when
 * there is no filter text being typed.
 */
export function ItemList({
  items,
  filter,
  digits = true,
  onEnterText,
}: {
  items: Item[];
  filter?: string;
  digits?: boolean;
  /** Called on Enter when the filter text should be submitted instead. */
  onEnterText?: () => boolean;
}) {
  const [at, setAt] = useState(() =>
    Math.max(
      0,
      items.findIndex((i) => i.active),
    ),
  );
  const itemsRef = useRef(items);
  itemsRef.current = items;
  const atRef = useRef(at);
  atRef.current = at;

  useEffect(() => {
    if (filter !== undefined) setAt(0);
  }, [filter]);

  useEffect(() => {
    const choose = (i: Item | undefined) => {
      if (!i) return;
      i.onSelect();
      if (!i.keepOpen) useUI.getState().closeMenu();
    };
    const onKey = (e: KeyboardEvent) => {
      const list = itemsRef.current;
      if (e.key === "ArrowDown" || (e.key === "j" && !filter && filter !== "")) {
        e.preventDefault();
        setAt((a) => Math.min(list.length - 1, a + 1));
      } else if (e.key === "ArrowUp" || (e.key === "k" && !filter && filter !== "")) {
        e.preventDefault();
        setAt((a) => Math.max(0, a - 1));
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (onEnterText?.()) return;
        choose(list[atRef.current]);
      } else if (digits && !filter && /^[1-9]$/.test(e.key) && !e.metaKey && !e.ctrlKey) {
        const i = list[Number(e.key) - 1];
        if (i) {
          e.preventDefault();
          choose(i);
        }
      } else {
        return;
      }
      e.stopPropagation();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [digits, filter, onEnterText]);

  if (!items.length) return <div className="px-3 py-2 text-[12.5px] text-ink3">No matches</div>;

  return (
    <div role="listbox" tabIndex={-1} className="scroll-thin max-h-[320px] overflow-y-auto">
      {items.map((item, i) => (
        <div
          key={item.key}
          role="option"
          aria-selected={i === at}
          tabIndex={-1}
          onMouseEnter={() => setAt(i)}
          onClick={() => {
            item.onSelect();
            if (!item.keepOpen) useUI.getState().closeMenu();
          }}
          onKeyDown={() => {}}
          className={`mx-1 flex h-9 cursor-default items-center gap-2.5 rounded-md px-2.5 text-[13.5px] desk:h-8 desk:text-[13px] ${
            i === at ? "bg-hover text-ink" : "text-ink2"
          }`}
        >
          <span className="flex w-4 justify-center">{item.icon}</span>
          <span className="min-w-0 flex-1 truncate">{item.label}</span>
          {item.hint && <span className="text-[12px] text-ink3">{item.hint}</span>}
          {item.active && <IconCheck size={14} className="text-accent" />}
          {digits && !filter && i < 9 && (
            <span className="hidden w-3 text-right text-[11px] tabular-nums text-ink3 desk:inline">
              {i + 1}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

function FilterInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  return (
    <div className="border-b border-line px-3 pb-1.5 pt-1">
      <input
        // biome-ignore lint/a11y/noAutofocus: menus open to type
        autoFocus
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-8 w-full text-[14px] outline-none desk:text-[13px]"
      />
    </div>
  );
}

function useFirst(ids: number[]) {
  const qc = useQueryClient();
  return findTask(qc, ids[0]);
}

function StatusMenu({ ids }: { ids: number[] }) {
  const actions = useTaskActions();
  const first = useFirst(ids);
  const items: Item[] = STATUSES.map((s) => ({
    key: s.value,
    label: s.label,
    icon: <StatusIcon status={s.value} />,
    active: ids.length === 1 && first?.status === s.value,
    hint: s.value === "done" && first?.recurrence ? "completes this run" : undefined,
    onSelect: () => actions.setStatus(ids, s.value),
  }));
  return <ItemList items={items} />;
}

function PriorityMenu({ ids }: { ids: number[] }) {
  const actions = useTaskActions();
  const first = useFirst(ids);
  // Linear order: urgent first, "no priority" last.
  const order = [1, 2, 3, 4, 0];
  const items: Item[] = order.map((p) => {
    const def = PRIORITIES.find((x) => x.value === p);
    return {
      key: String(p),
      label: def?.label ?? "",
      icon: <PriorityIcon priority={p} />,
      active: ids.length === 1 && first?.priority === p,
      onSelect: () => actions.patch(ids, { priority: p as 0 | 1 | 2 | 3 | 4 }),
    };
  });
  return <ItemList items={items} />;
}

function LabelsMenu({ ids }: { ids: number[] }) {
  const qc = useQueryClient();
  const lookups = useLookups();
  const actions = useTaskActions();
  const createLabel = useCreateLabel();
  const [filter, setFilter] = useState("");
  // Re-read on every render so toggles show immediately (the cache is optimistic).
  const tasks = ids.map((id) => findTask(qc, id)).filter((t) => t !== undefined);
  const has = (labelId: number) =>
    tasks.length > 0 && tasks.every((t) => t.label_ids.includes(labelId));
  const [, force] = useState(0);

  const toggle = (labelId: number) => {
    const on = has(labelId);
    for (const t of tasks) {
      const next = on
        ? t.label_ids.filter((x) => x !== labelId)
        : [...new Set([...t.label_ids, labelId])];
      actions.patch([t.id], { label_ids: next });
    }
    force((n) => n + 1);
  };

  const q = filter.trim().toLowerCase();
  const labels = [...lookups.labels.values()]
    .filter((l) => l.name.toLowerCase().includes(q))
    .sort((a, b) => a.name.localeCompare(b.name));
  const items: Item[] = labels.map((l) => ({
    key: String(l.id),
    label: l.name,
    icon: <Dot color={l.color} />,
    active: has(l.id),
    keepOpen: true,
    onSelect: () => toggle(l.id),
  }));
  if (q && !labels.some((l) => l.name.toLowerCase() === q)) {
    items.push({
      key: "new",
      label: `Create label ‘${filter.trim()}’`,
      icon: <IconPlus size={14} />,
      keepOpen: true,
      onSelect: () =>
        createLabel.mutate(filter.trim(), {
          onSuccess: (l) => {
            for (const t of tasks) actions.patch([t.id], { label_ids: [...t.label_ids, l.id] });
            setFilter("");
          },
        }),
    });
  }
  return (
    <>
      <FilterInput value={filter} onChange={setFilter} placeholder="Find or create a label" />
      <ItemList items={items} filter={filter} />
    </>
  );
}

function DueMenu({ ids }: { ids: number[] }) {
  const today = useToday();
  const actions = useTaskActions();
  const first = useFirst(ids);
  const [text, setText] = useState("");
  const parsed = useParse(text);
  const data = text.trim() ? parsed.data : undefined;
  const textRef = useRef(text);
  textRef.current = text;

  const items: Item[] = today
    ? [
        ...quickDates(today).map((d) => ({
          key: d.label,
          label: d.label,
          icon: <IconCalendar size={14} />,
          hint: d.hint,
          active: ids.length === 1 && first?.due_date === d.date,
          onSelect: () => actions.patch(ids, { due_date: d.date }),
        })),
        {
          key: "none",
          label: "No date",
          icon: <IconClose size={14} />,
          onSelect: () => actions.patch(ids, { due_date: null, due_time: null }),
        },
      ]
    : [];

  const onEnterText = useMemo(
    () => () => {
      const value = textRef.current.trim();
      if (!value) return false;
      actions.patch(ids, { due_string: value });
      useUI.getState().closeMenu();
      return true;
    },
    [actions, ids],
  );

  return (
    <>
      <div className="border-b border-line px-3 pb-2 pt-1">
        <input
          // biome-ignore lint/a11y/noAutofocus: the due menu opens to type a date
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Type a date: next fri 5pm, dec 3, every mon"
          className="h-8 w-full text-[14px] outline-none desk:text-[13px]"
        />
        {text.trim() && (
          <div className="flex items-center gap-1.5 text-[12px] text-ink2">
            {data?.recurrence ? (
              <>
                <IconRepeat size={12} />
                {data.recurrence.text}
                {data.due_date && today ? `, first ${formatDue(data.due_date, today)}` : ""}
              </>
            ) : data?.due_date && today ? (
              <>
                <IconCalendar size={12} />
                {formatDue(data.due_date, today)} {formatTime(data.due_time)}
              </>
            ) : (
              <span className="text-ink3">No date recognized yet</span>
            )}
            <span className="ml-auto text-ink3">
              <kbd className="kbd">↵</kbd>
            </span>
          </div>
        )}
      </div>
      <ItemList items={items} filter={text} digits={false} onEnterText={onEnterText} />
    </>
  );
}

function ProjectMenu({ ids }: { ids: number[] }) {
  const lookups = useLookups();
  const actions = useTaskActions();
  const first = useFirst(ids);
  const [filter, setFilter] = useState("");
  const q = filter.trim().toLowerCase();
  const match = (name: string) => name.toLowerCase().includes(q);
  const items: Item[] = [];
  if (match("inbox")) {
    items.push({
      key: "inbox",
      label: "Inbox",
      icon: <IconInbox size={14} />,
      active: ids.length === 1 && !first?.project_id && !first?.area_id,
      onSelect: () => actions.patch(ids, { project_id: null, area_id: null }),
    });
  }
  const areas = [...lookups.areas.values()].sort((a, b) => a.position - b.position);
  const projects = [...lookups.projects.values()].filter(
    (p) => p.status !== "done" && p.status !== "canceled",
  );
  for (const area of [...areas, null]) {
    if (area && match(area.name)) {
      items.push({
        key: `a${area.id}`,
        label: area.name,
        icon: <Dot color={area.color} />,
        hint: "area",
        active: ids.length === 1 && first?.area_id === area.id && !first?.project_id,
        onSelect: () => actions.patch(ids, { project_id: null, area_id: area.id }),
      });
    }
    for (const p of projects.filter((p) => p.area_id === (area?.id ?? null))) {
      if (!match(p.name) && !(area && match(area.name))) continue;
      items.push({
        key: `p${p.id}`,
        label: (
          <>
            {area && <span className="text-ink3">{area.name} / </span>}
            {p.name}
          </>
        ),
        icon: <Dot color={p.color ?? area?.color ?? "rgb(var(--ink3))"} size={7} />,
        active: ids.length === 1 && first?.project_id === p.id,
        onSelect: () => actions.patch(ids, { project_id: p.id }),
      });
    }
  }
  return (
    <>
      <FilterInput value={filter} onChange={setFilter} placeholder="Move to project or area" />
      <ItemList items={items} filter={filter} />
    </>
  );
}
