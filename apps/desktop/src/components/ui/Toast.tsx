import { forwardRef, useEffect, useRef } from "react";
import { common } from "../../i18n/zh-CN/common";
import { Icon } from "./Icon";
import { Button } from "./Button";

export interface ToastProps { tone: "success" | "error"; text: string; onClose: () => void; }
export const TOAST_MS = 4000;

export const Toast = forwardRef<HTMLDivElement, ToastProps>(function Toast({ tone, text, onClose }, ref) {
  const callback = useRef(onClose);
  useEffect(() => { callback.current = onClose; }, [onClose]);
  useEffect(() => {
    if (tone === "error") return;
    const timer = window.setTimeout(() => callback.current(), TOAST_MS);
    return () => window.clearTimeout(timer);
  }, [tone, text]);
  return <div ref={ref} className={`c-toast${tone === "error" ? " c-toast--error" : ""}`}
    role={tone === "error" ? "alert" : "status"}>
    <Icon name={tone === "error" ? "alert-triangle" : "check"} /><div className="c-toast__text">{text}</div>
    <Button variant="icon" icon="x" aria-label={common.dismiss} onClick={onClose} />
  </div>;
});
