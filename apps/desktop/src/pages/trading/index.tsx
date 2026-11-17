import { useState } from "react";
import { useAppStore } from "../../app/store";
import { Banner, Button, Skeleton } from "../../components/ui";
import { trading as t } from "../../i18n/zh-CN/trading";
import { PageFrame } from "../../shell/PageFrame";
import { AccountBar } from "./AccountBar";
import { CreateAccountForm } from "./CreateAccountForm";
import { OrderPanel } from "./OrderPanel";
import { OrdersTable, type Tab } from "./OrdersTable";
import { PortfolioCards } from "./PortfolioCards";
import { ResetAccountModal } from "./ResetAccountModal";
import { usePaper } from "./usePaper";
import "./trading.css";

export default function TradingPage() {
  const client = useAppStore(state => state.client);
  const bootstrap = useAppStore(state => state.bootstrap.value);
  const paper = usePaper(client);
  const [tab, setTab] = useState<Tab>("pending"), [creating, setCreating] = useState(false), [resetOpen, setResetOpen] = useState(false);
  const activeTab = paper.highlight ? "history" : tab;
  return <PageFrame><section className="p-trading" data-ready={!paper.loading}>
    <header className="p-page__head"><h1 className="p-page__title">{t.title}</h1>
      <Button icon="refresh-cw" disabled={paper.busy || paper.loading || !client} onClick={() => { void paper.refresh(); }}>{t.refresh}</Button></header>
    {!client && <Banner tone="info" text={t.coreWaiting} />}
    {paper.error && <Banner tone={paper.error.code === "DATA_INSUFFICIENT" || paper.error.code === "TIMEOUT" ? "warn" : "danger"}
      text={`${paper.error.message}${paper.highlight ? ` ${t.orderId} ${paper.highlight}` : ""}`} />}
    {paper.account && <AccountBar accounts={paper.accounts} account={paper.account} busy={paper.busy}
      blocked={!!paper.unresolved || paper.loading || !paper.portfolio} onSelect={id => { setCreating(false); setResetOpen(false); paper.select(id); }}
      onAdvance={() => { void paper.advance().then(() => setTab("fills")).catch(() => {}); }} onReset={() => setResetOpen(true)} onCreate={() => setCreating(true)} />}
    {client && !paper.loading && (creating || !paper.account) ? <CreateAccountForm defaultDate={paper.account?.clockDate ?? bootstrap?.now.slice(0, 10) ?? ""}
      busy={paper.busy} onCreate={async input => { await paper.create(input); setCreating(false); }} onCancel={paper.account ? () => setCreating(false) : undefined} /> :
      client && <><PortfolioCards portfolio={paper.portfolio} />
        {paper.portfolio ? <div className="p-trading__main"><OrderPanel key={paper.portfolio.account.accountId} client={client} portfolio={paper.portfolio}
          orders={paper.orders} busy={paper.busy} unresolved={paper.unresolved} onSubmit={paper.place} />
          <div className="p-trading__ledger"><OrdersTable tab={activeTab} orders={paper.orders} positions={paper.portfolio.positions}
            busy={paper.busy || !!paper.unresolved} highlight={paper.highlight} onTab={value => { paper.clearHighlight(); setTab(value); }} onCancel={paper.cancel} />
            <p className="c-note u-mt-3">{t.feeHelp}</p></div></div> : paper.loading && <div aria-label={t.waiting}><Skeleton /></div>}
      </>}
    {paper.account && resetOpen && <ResetAccountModal key={paper.account.accountId} account={paper.account} open busy={paper.busy}
      onReset={paper.reset} onClose={() => setResetOpen(false)} />}
  </section></PageFrame>;
}
