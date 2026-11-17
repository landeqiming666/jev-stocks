import { useCallback, useEffect, useRef, useState } from "react";
import { ROUTE_EVENT } from "../../router/useRoute";
import { notifyToast } from "../../app/events";
import { holdings as text } from "../../i18n/zh-CN/holdings";

export function useExitGuard(dirty: boolean, busy: boolean) {
  const state = useRef({ dirty, busy }); state.current = { dirty, busy };
  const hash = useRef(window.location.hash);
  const [pending, setPending] = useState<(() => void) | null>(null);
  const request = useCallback((action: () => void) => {
    if (state.current.busy) { notifyToast("info", text.saving); return; }
    if (state.current.dirty) setPending(() => action); else action();
  }, []);
  useEffect(() => {
    function unload(event: BeforeUnloadEvent) {
      if (state.current.dirty || state.current.busy) { event.preventDefault(); event.returnValue = ""; }
    }
    function route(event: Event) {
      const next = window.location.hash;
      if (next === hash.current) return;
      if (state.current.dirty || state.current.busy) {
        event.stopImmediatePropagation();
        window.history.replaceState(null, "", hash.current);
        request(() => {
          hash.current = next;
          window.history.replaceState(null, "", next);
          window.dispatchEvent(new Event(ROUTE_EVENT));
        });
      } else hash.current = next;
    }
    window.addEventListener("beforeunload", unload);
    for (const name of ["hashchange", "popstate", ROUTE_EVENT]) window.addEventListener(name, route, true);
    return () => {
      window.removeEventListener("beforeunload", unload);
      for (const name of ["hashchange", "popstate", ROUTE_EVENT]) window.removeEventListener(name, route, true);
    };
  }, [request]);
  return { request, pending, cancel: () => setPending(null), discard: () => {
    const action = pending; setPending(null); state.current.dirty = false; action?.();
  } };
}
