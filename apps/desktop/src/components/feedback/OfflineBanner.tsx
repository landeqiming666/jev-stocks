import { useEffect, useRef } from "react";
import { useAppStore } from "../../app/store";
import { feedback } from "../../i18n/zh-CN/feedback";
import { useOnline } from "../../lib/online";
import { pushToast } from "../../lib/toast-store";
import { Banner } from "../ui";

export function OfflineBanner() {
  const online = useOnline();
  const bootstrapOffline = useAppStore(state => state.bootstrap.value?.offline ?? false);
  const offline = !online || bootstrapOffline;
  const previous = useRef(offline);
  useEffect(() => {
    if (previous.current && !offline) pushToast({ tone: "success", text: feedback.online });
    previous.current = offline;
  }, [offline]);
  return offline ? <Banner tone="warn" text={feedback.offline} /> : null;
}
