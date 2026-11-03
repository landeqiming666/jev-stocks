import { forwardRef, type ReactNode } from "react";
import type { Tone } from "./types";

export interface StatusTagProps { tone: Tone; children: ReactNode; }
export const StatusTag = forwardRef<HTMLSpanElement, StatusTagProps>(function StatusTag({ tone, children }, ref) {
  return <span ref={ref} data-ui className={`c-tag c-tag--${tone}`}>{children}</span>;
});
