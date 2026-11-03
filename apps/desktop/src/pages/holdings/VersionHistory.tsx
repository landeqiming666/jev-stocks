import { useCallback, useId } from "react";
import { useAppStore } from "../../app/store";
import { Banner, Button, Modal } from "../../components/ui";
import { holdings as text } from "../../i18n/zh-CN/holdings";
import { formatDateTime } from "../../app/format";
import { RpcError } from "../../rpc";
import { useResource } from "./use-resource";

export function VersionHistory({ thesisId, onClose }: { thesisId: string; onClose: () => void }) {
  const client = useAppStore(s => s.client), id = useId();
  const fetch = useCallback((signal: AbortSignal) => client ? client.call("thesis.versions", { thesisId }, { signal }) :
    Promise.reject(new RpcError("INTERNAL", text.disconnected)), [client, thesisId]);
  const resource = useResource(fetch);
  return <Modal open titleId={id} onClose={onClose}>
    <h2 id={id}>{text.versions}</h2>
    {resource.loading && <p role="status">{text.loading}</p>}
    {resource.error && <Banner tone="danger" text={resource.error} action={<Button onClick={() => void resource.refresh()}>{text.retry}</Button>} />}
    <div className="p-holdings__history">{resource.value?.items.map(version => <article key={version.version}>
      <h3>{text.version(version.version, resource.value!.items.length)}</h3><p>{version.statement}</p>
      {version.killCondition && <p className="u-muted">{text.killPrefix}{version.killCondition}</p>}
      <time dateTime={version.createdAt}>{text.created} {formatDateTime(version.createdAt)}</time>
    </article>)}</div>
    <Button onClick={onClose}>{text.close}</Button>
  </Modal>;
}
