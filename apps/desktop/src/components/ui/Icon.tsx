import { forwardRef } from "react";
import type { IconName } from "./types";

export interface IconProps { name: IconName; size?: 16 | 20; label?: string; }

const paths = {
  "sun": <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" /></>,
  "briefcase": <><rect x="2" y="7" width="20" height="14" rx="2" /><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" /></>,
  "arrow-left-right": <><path d="M8 3 4 7l4 4M4 7h16M16 21l4-4-4-4M20 17H4" /></>,
  "activity": <><path d="M22 12h-4l-3 9L9 3l-3 9H2" /></>,
  "radar": <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><path d="M12 12 19 5" /></>,
  "settings": <><path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6" /></>,
  "search": <><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></>,
  "x": <><path d="M18 6 6 18M6 6l12 12" /></>,
  "chevron-down": <><path d="m6 9 6 6 6-6" /></>,
  "chevron-right": <><path d="m9 6 6 6-6 6" /></>,
  "external-link": <><path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /></>,
  "check": <><path d="M20 6 9 17l-5-5" /></>,
  "alert-triangle": <><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3M12 9v4M12 17h.01" /></>,
  "info": <><circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" /></>,
  "refresh-cw": <><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8M21 3v5h-5M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16M8 16H3v5" /></>,
  "play": <><path d="m6 3 14 9-14 9z" /></>,
  "more-horizontal": <><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /><circle cx="5" cy="12" r="1" /></>,
  "wifi-off": <><path d="M12 20h.01M8.5 16.4a5 5 0 0 1 7 0M2 8.8a15 15 0 0 1 4.2-2.6M22 8.8a15 15 0 0 0-8.5-3.7M5 12.9a10 10 0 0 1 5.2-2.7M19 12.9a10 10 0 0 0-2.3-1.7M2 2l20 20" /></>,
  "clock": <><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></>,
  "plus": <><path d="M12 5v14M5 12h14" /></>,
  "arrow-down": <><path d="M12 5v14M19 12l-7 7-7-7" /></>,
  "minus": <><path d="M5 12h14" /></>,
  "help-circle": <><circle cx="12" cy="12" r="10" /><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3M12 17h.01" /></>,
} satisfies Record<IconName, React.ReactNode>;

export const Icon = forwardRef<SVGSVGElement, IconProps>(function Icon({ name, size = 16, label }, ref) {
  return <svg ref={ref} data-ui className={`c-icon${size === 20 ? " c-icon--20" : ""}`}
    viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden={label ? undefined : true}
    aria-label={label} role={label ? "img" : undefined} focusable="false">{paths[name]}</svg>;
});
