import { useEffect, useLayoutEffect, useRef } from "react";
export type DraftState = (dirty: boolean, busy: boolean) => void;
export function useDraft(dirty: boolean, busy: boolean, onState?: DraftState) {
  const field = useRef<HTMLTextAreaElement | HTMLInputElement | null>(null);
  useEffect(() => { onState?.(dirty, busy); }, [dirty, busy, onState]);
  useEffect(() => () => onState?.(false, false), [onState]);
  useLayoutEffect(() => {
    const origin = document.activeElement;
    field.current?.focus();
    return () => { if (origin instanceof HTMLElement && origin.isConnected) origin.focus({ preventScroll: true }); };
  }, []);
  return field;
}
