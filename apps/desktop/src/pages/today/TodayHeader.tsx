import type { Bootstrap, Inbox } from "../../rpc";
import { formatTime } from "../../app/format";
import { today } from "../../i18n/zh-CN/today";
import { Button } from "../../components/ui";

export function TodayHeader({ boot, inbox, title, start, cancel, running, starting, cancelling, conflict, loading }: {
  boot: Bootstrap; inbox: Inbox | null; title?: string; start: () => Promise<void>; cancel: () => Promise<void>;
  running: boolean; starting: boolean; cancelling: boolean; conflict: boolean; loading: boolean;
}) {
  const date = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric" }).format(new Date(boot.now));
  const weekday = new Intl.DateTimeFormat("zh-CN", { weekday: "long" }).format(new Date(boot.now));
  const reason = !boot.configured.jevKey || !boot.configured.secEmail ? today.configRequired :
    boot.offline || inbox?.dataStatus.offline ? today.offlineScan : inbox?.setup.scannableInstruments === 0 ? today.noHoldings : undefined;
  const scan = inbox?.lastScan;
  return <header className="p-page__head"><div><p className="p-page__eyebrow">{date} {weekday}{inbox && ` · ${today.market} ${today.marketState[inbox.dataStatus.marketState]}`}</p>
    {title && <h1 className="p-page__title" tabIndex={-1}>{title}</h1>}</div>
    <div className="p-page__actions"><span className="p-page__sub">{scan ? `${scan.status === "failed" ? today.scanFailed : today.lastScan} ${scan.finishedAt ? formatTime(scan.finishedAt) : "—"}` : today.notScanned}</span>
      {running ? <Button disabled={cancelling} onClick={() => { void cancel(); }}>{cancelling ? today.cancelling : today.cancel}</Button> :
        <Button variant="primary" loading={starting} disabled={!!reason || loading || conflict} disabledReason={conflict ? today.scanConflict : reason} onClick={() => { void start(); }}>{today.scan}</Button>}
    </div>
  </header>;
}
