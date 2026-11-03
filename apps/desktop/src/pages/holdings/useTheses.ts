import { useCallback } from "react";
import { RpcError, type RpcClient } from "../../rpc";
import { holdings as text } from "../../i18n/zh-CN/holdings";
import { useResource } from "./use-resource";

export function useTheses(client: RpcClient | null, instrumentId: string) {
  const fetch = useCallback((signal: AbortSignal) => {
    if (!client) return Promise.reject(new RpcError("INTERNAL", text.disconnected));
    return client.call("thesis.list", { instrumentId, status: "active" }, { signal });
  }, [client, instrumentId]);
  const resource = useResource(fetch);
  return { ...resource, items: resource.value?.items.filter(t => t.status === "active" && t.instrumentId === instrumentId) ?? [] };
}
