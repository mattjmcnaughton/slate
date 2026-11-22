import { useSyncExternalStore } from "react";

const PHONE = "(max-width: 640px)";

function subscribe(cb: () => void) {
  const mq = window.matchMedia(PHONE);
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
}

/** True at phone width (<= 640px), where the layout is a single column. */
export function useIsPhone(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(PHONE).matches,
    () => false,
  );
}

export const isPhone = () => window.matchMedia(PHONE).matches;
