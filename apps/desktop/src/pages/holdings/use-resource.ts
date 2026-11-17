import { useCallback, useEffect, useRef, useState } from "react";
import { holdings as text } from "../../i18n/zh-CN/holdings";
import { RpcError } from "../../rpc";

export function errorText(error: unknown, fallback: string = text.loadFailed): string {
  return error instanceof RpcError ? text.errors[error.code as keyof typeof text.errors] ?? fallback : fallback;
}
export function useResource<T>(fetch: (signal: AbortSignal) => Promise<T>) {
  const [value, setValue] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setLoading(true); setError(null);
    try {
      const result = await fetch(controller.signal);
      if (!controller.signal.aborted) setValue(result);
    } catch (error) {
      if (!controller.signal.aborted) setError(errorText(error));
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [fetch]);
  useEffect(() => { setValue(null); void refresh(); return () => request.current?.abort(); }, [refresh]);
  return { value, loading, error, refresh };
}
