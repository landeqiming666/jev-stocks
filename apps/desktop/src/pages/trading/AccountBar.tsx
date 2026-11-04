import { Button } from "../../components/ui";
import { trading as t } from "../../i18n/zh-CN/trading";
import type { PaperAccount } from "../../rpc";
import { dateText } from "./validation";

export function AccountBar({ accounts, account, busy, blocked, onSelect, onAdvance, onReset, onCreate }: {
  accounts: PaperAccount[]; account: PaperAccount; busy: boolean; blocked: boolean;
  onSelect: (id: string) => void; onAdvance: () => void; onReset: () => void; onCreate: () => void;
}) {
  return <div className="p-trading__account"><div className="u-grow">
    <label className="u-small u-muted" htmlFor="acc-select">{t.account}</label>
    <select className="c-select u-w-180" id="acc-select" value={account.accountId} onChange={event => onSelect(event.target.value)}>
      {accounts.map(item => <option key={item.accountId} value={item.accountId}>{item.name}</option>)}
    </select><span>{t.clock} <span className="p-trading__clock">{dateText(account.clockDate)}</span></span>
  </div><Button variant="text" disabled={busy || blocked} onClick={onCreate}>{t.addAccount}</Button>
    <Button variant="primary" icon="play" disabled={blocked} loading={busy} onClick={onAdvance} disabledReason={t.intentHelp}>{t.advance}</Button>
    <Button variant="danger" disabled={busy || blocked} onClick={onReset} disabledReason={t.intentHelp}>{t.reset}</Button>
  </div>;
}
