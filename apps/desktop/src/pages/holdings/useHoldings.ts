import { useCallback } from "react";
import { holdings as text } from "../../i18n/zh-CN/holdings";
import { RpcError, type RpcClient, type ParamsOf } from "../../rpc";
import { useResource } from "./use-resource";

export function useHoldings(client: RpcClient | null) {
  const fetch = useCallback((signal: AbortSignal) => {
    if (!client) return Promise.reject(new RpcError("INTERNAL", text.disconnected));
    return client.call("holdings.list", {}, { signal });
  }, [client]);
  const resource = useResource(fetch);
  return { ...resource, items: resource.value?.items.filter(h => h.instrument.market === "us") ?? [],
    upsert: async (input: ParamsOf<"holdings.upsert">) => {
      if (!client) throw new RpcError("INTERNAL", text.disconnected);
      const result = await client.call("holdings.upsert", input);
      await resource.refresh(); return result;
    },
    archive: async (instrumentId: string) => {
      if (!client) throw new RpcError("INTERNAL", text.disconnected);
      await client.call("holdings.archive", { instrumentId });
      await resource.refresh();
    },
  };
}
