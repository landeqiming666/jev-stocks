import { useEffect, useRef } from "react";
export function useFocusReturn() {
  const frame = useRef<number | null>(null);
  useEffect(() => () => { if (frame.current !== null) cancelAnimationFrame(frame.current); }, []);
  return (id: string) => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => { document.getElementById(id)?.focus({ preventScroll: true }); frame.current = null; });
  };
}
