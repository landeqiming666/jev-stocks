import { useEffect, useState } from "react";
import { getRpcClient, type RpcClient } from "../rpc";
import { RouterView } from "../router/RouterView";
import { AppShell } from "../shell/AppShell";
import { startApp } from "./bootstrap";

export function Application({ createClient = getRpcClient }: { createClient?: () => RpcClient }) {
  const [attempt, retry] = useState(0);
  useEffect(() => startApp(createClient()), [attempt, createClient]);
  return <AppShell onRetry={() => retry(attempt => attempt + 1)}><RouterView /></AppShell>;
}
