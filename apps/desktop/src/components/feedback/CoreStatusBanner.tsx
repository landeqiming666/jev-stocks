import { useEffect, useState } from "react";
import { useAppStore } from "../../app/store";
import { feedback } from "../../i18n/zh-CN/feedback";
import { subscribeCoreStatus, type CoreStatusListener } from "../../lib/core-status";
import type { CoreStatus, RpcClient } from "../../rpc/client";
import { Banner, Button } from "../ui";

function ClientBanner({ client, listener, onRetry }: { client: RpcClient; listener?: CoreStatusListener; onRetry?: () => void }) {
  const [value, setValue] = useState<{ client: RpcClient; state: CoreStatus | null } | null>(null);
  const bootstrapStatus = useAppStore(state => state.bootstrap.status);
  useEffect(() => {
    let last: CoreStatus | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const off = subscribeCoreStatus(client, next => {
      if (next === last) return;
      clearTimeout(timer);
      setValue({ client, state: next === "ready" && last === null ? null : next });
      if (next === "ready" && last !== null) timer = setTimeout(() => setValue({ client, state: null }), 3000);
      last = next;
    }, listener);
    return () => { off(); clearTimeout(timer); };
  }, [client, listener, bootstrapStatus]);
  const state = value?.client === client ? value.state : null;
  if (!state) return null;
  const text = state === "starting" ? feedback.coreStarting : state === "restarting" ? feedback.coreRestarting :
    state === "failed" ? feedback.coreFailed : feedback.coreReady;
  return <Banner tone={state === "failed" ? "danger" : state === "ready" ? "info" : "warn"} text={text}
    action={state === "failed" && onRetry ? <Button onClick={onRetry}>{feedback.retry}</Button> : undefined} />;
}
export function CoreStatusBanner({ listener, onRetry }: { listener?: CoreStatusListener; onRetry?: () => void }) {
  const client = useAppStore(state => state.client);
  return client ? <ClientBanner client={client} listener={listener} onRetry={onRetry} /> : null;
}
