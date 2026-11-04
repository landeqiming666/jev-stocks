import { useEffect } from "react";
import { Toast } from "../ui";
import { feedback } from "../../i18n/zh-CN/feedback";
import { dismissToast, getToasts, useToasts } from "../../lib/toast-store";
import "./feedback.css";

export function ToastViewport() {
  const items = useToasts();
  useEffect(() => {
    function escape(event: KeyboardEvent) {
      if (event.key !== "Escape" || event.defaultPrevented || event.isComposing) return;
      const newest = getToasts().at(-1);
      if (newest) { event.preventDefault(); dismissToast(newest.id); }
    }
    // U-01 的 document capture 浮层先处理 Esc；冒泡到 window 才轮到 Toast。
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, []);
  return <section className="c-toast-stack c-feedback-toasts" aria-label={feedback.notifications}>
    {items.map(item => <Toast key={`${item.id}:${item.createdAt}`} tone={item.tone} text={item.text}
      onClose={() => dismissToast(item.id)} />)}
  </section>;
}
