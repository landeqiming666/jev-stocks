import { useEffect, useLayoutEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { TOAST_EVENT, type ToastDetail } from "../../app/events";
import { ownValue } from "../../lib/errors";
import { feedbackRootServerSnapshot, feedbackRootSnapshot, registerFeedbackHost, subscribeFeedbackRoot } from "../../lib/feedback-root";
import type { CoreStatusListener } from "../../lib/core-status";
import { pushToast } from "../../lib/toast-store";
import { ToastViewport } from "./ToastViewport";
import { OfflineBanner } from "./OfflineBanner";
import { CoreStatusBanner } from "./CoreStatusBanner";
import { ErrorBoundary } from "./ErrorBoundary";

function GlobalFeedback({ listener, root, onCoreRetry }: { listener?: CoreStatusListener; root: HTMLElement; onCoreRetry?: () => void }) {
  useEffect(() => {
    function notify(event: Event) {
      const detail: unknown = (event as CustomEvent<ToastDetail>).detail;
      const text = ownValue(detail, "text"), tone = ownValue(detail, "tone");
      if (typeof text !== "string" || !text.trim()) return;
      if (tone === "success" || tone === "ok") pushToast({ tone: "success", text });
      else if (tone === "error" || tone === "danger" || tone === "warn") pushToast({ tone: "error", text });
    }
    window.addEventListener(TOAST_EVENT, notify);
    return () => window.removeEventListener(TOAST_EVENT, notify);
  }, []);
  return <><div className="c-feedback-banners"><OfflineBanner /><CoreStatusBanner listener={listener} onRetry={onCoreRetry} /></div>
    {createPortal(<ToastViewport />, root)}</>;
}
export function FeedbackHost({ children, coreStatusListener, onCoreRetry }: {
  children: ReactNode; coreStatusListener?: CoreStatusListener; onCoreRetry?: () => void;
}) {
  const [token] = useState(() => Symbol("feedback-host"));
  const snapshot = useSyncExternalStore(subscribeFeedbackRoot, feedbackRootSnapshot, feedbackRootServerSnapshot);
  useLayoutEffect(() => registerFeedbackHost(token), [token]);
  return <div className="c-feedback-frame">
    {snapshot?.owner === token && <GlobalFeedback root={snapshot.root} listener={coreStatusListener} onCoreRetry={onCoreRetry} />}
    <div className="c-feedback-page"><ErrorBoundary>{children}</ErrorBoundary></div>
  </div>;
}
