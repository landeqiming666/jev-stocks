import { useEffect, useState, type ReactNode } from "react";
import { getRpcClient, type RpcClient } from "../rpc";
import { RouterView } from "../router/RouterView";
import { AppShell } from "../shell/AppShell";
import { startApp } from "./bootstrap";
import { FeedbackHost } from "../components/feedback";

export function Application({ createClient = getRpcClient, view }: { createClient?: () => RpcClient; view?: ReactNode }) {
  const [attempt, retry] = useState(0);
  useEffect(() => startApp(createClient()), [attempt, createClient]);
  const onRetry = () => retry(attempt => attempt + 1);
  return <AppShell onRetry={onRetry} globalFeedback><FeedbackHost onCoreRetry={onRetry}>
    {view ?? <RouterView />}
  </FeedbackHost></AppShell>;
}
