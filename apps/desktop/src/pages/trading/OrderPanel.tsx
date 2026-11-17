import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Banner, Button, Field, Input, SearchInput, SegmentedControl } from "../../components/ui";
import { trading as t } from "../../i18n/zh-CN/trading";
import { RpcError, type Instrument, type PaperOrder, type Portfolio, type RpcClient } from "../../rpc";
import { type PendingIntent, type PlaceOrderInput } from "./order-intents";
import { formatDecimal, moneyText, validateOrder } from "./validation";

export const QTY_STEP = 1;
export const ESTIMATE_DECIMALS = 2;
export function OrderPanel({ client, portfolio, orders, busy, unresolved, onSubmit }: {
  client: RpcClient; portfolio: Portfolio; orders: PaperOrder[]; busy: boolean; unresolved: PendingIntent | null;
  onSubmit: (input: PlaceOrderInput) => Promise<unknown>;
}) {
  const [selected, setSelected] = useState<Instrument | null>(null);
  const [query, setQuery] = useState(""); const [results, setResults] = useState<Instrument[]>([]);
  const [searching, setSearching] = useState(false), [searched, setSearched] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [active, setActive] = useState(-1);
  const [side, setSide] = useState<"buy" | "sell">("buy"), [quantity, setQuantity] = useState("100");
  const [error, setError] = useState<string | null>(null);
  const submitLock = useRef(false); const searchRef = useRef<HTMLInputElement>(null);
  const locked = busy || !!unresolved;
  const inputSide = unresolved?.params.side ?? side;
  const inputQuantity = unresolved ? String(unresolved.params.quantity) : quantity;
  const position = portfolio.positions.find(position => position.instrument.instrumentId === selected?.instrumentId);
  const pendingSells = orders.filter(order => order.status === "pending" && order.side === "sell" &&
    order.instrument.instrumentId === selected?.instrumentId).reduce((sum, order) => sum + order.quantity, 0);
  const sellable = Math.max(0, (position?.sellableQuantity ?? 0) - pendingSells);
  const reference = [...orders].filter(order => order.instrument.instrumentId === selected?.instrumentId && order.estimate)
    .sort((a, b) => b.createdClockDate.localeCompare(a.createdClockDate) || b.orderId.localeCompare(a.orderId))[0];
  useEffect(() => {
    setResults([]); setSearched(false); setSearching(false); setSearchError(null); setActive(-1);
    if (!query.trim() || selected || locked) return;
    const controller = new AbortController(); let live = true;
    const timer = setTimeout(() => {
      setSearching(true);
      void client.call("instruments.search", { query: query.trim(), limit: 20 }, { signal: controller.signal }).then(result => {
        if (live) { setResults(result.items.filter(item => item.market === "us" && item.currency === "USD" && item.isActive)); setSearched(true); }
      }).catch(error => { if (live && error instanceof RpcError && error.code !== "CANCELLED") setSearchError(error.message); })
        .finally(() => { if (live) setSearching(false); });
    }, 200);
    return () => { live = false; clearTimeout(timer); controller.abort(); };
  }, [client, query, selected, locked]);
  function choose(item: Instrument) { setSelected(item); setQuery(item.symbol); setResults([]); setError(null); setActive(-1); searchRef.current?.focus(); }
  function searchKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return;
    if (event.key === "Escape") { setResults([]); setActive(-1); return; }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault(); if (results.length) setActive((active + (event.key === "ArrowDown" ? 1 : -1) + results.length) % results.length);
    }
    if (event.key === "Enter" && results.length) { event.preventDefault(); choose(results[Math.max(0, active)]!); }
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy || submitLock.current) return;
    if (!unresolved) {
      const validation = validateOrder({ quantity, side, availableCash: portfolio.availableCash, sellable });
      if (!validation.ok) { setError(validation.message!); return; }
      if (!selected) { setError(t.instrumentRequired); searchRef.current?.focus(); return; }
    }
    submitLock.current = true; setError(null);
    try {
      await onSubmit(unresolved ? { instrumentId: unresolved.params.instrumentId, side: unresolved.params.side,
        quantity: unresolved.params.quantity, orderType: "market_open" } : { instrumentId: selected!.instrumentId,
        side, quantity: Number(quantity), orderType: "market_open" });
    } catch { /* RPC 错误由账户区域显示，避免重复横幅。 */ }
    finally { submitLock.current = false; }
  }
  return <form className="c-card p-trading__ticket" onSubmit={submit} noValidate>
    <h2 className="c-card__title">{t.order}</h2>{error && <Banner tone="danger" text={error} />}
    {unresolved && <Banner tone="warn" text={t.intentHelp} />}
    <div className="p-trading__search"><Field id="order-symbol" label={t.instrument}>
      <SearchInput ref={searchRef} value={unresolved?.params.instrumentId ?? query} disabled={locked} maxLength={64} placeholder={t.search}
        expanded={results.length > 0} aria-controls="order-symbol-list" aria-activedescendant={active >= 0 ? `order-result-${active}` : undefined}
        onKeyDown={searchKey} onChange={event => { setSelected(null); setQuery(event.target.value); setError(null); }} />
    </Field>{selected && <p className="c-note">{selected.name} · {selected.exchange}</p>}
      {results.length > 0 && <ul className="p-trading__results" role="listbox" id="order-symbol-list" aria-label={t.instrument}>
        {results.map((item, index) => <li key={item.instrumentId} id={`order-result-${index}`} role="option" aria-selected={active === index}
          className={active === index ? "is-active" : ""} onMouseDown={event => event.preventDefault()} onClick={() => choose(item)}>
          <strong className="u-mono">{item.symbol}</strong><span>{item.name}</span><small>{item.exchange}{item.nameZh ? ` · ${item.nameZh}` : ""}</small>
        </li>)}
      </ul>}
      {searching && <p className="c-note" role="status">{t.searching}</p>}
      {searched && !selected && !results.length && <p className="c-note" role="status">{t.noResults}</p>}
      {searchError && <p className="c-field__error" role="alert">{searchError}</p>}
    </div><div><div className="c-field__label u-mb-1">{t.direction}</div>
      <SegmentedControl name="side" label={t.direction} value={inputSide} items={[{ value: "buy", label: t.buy, disabled: locked }, { value: "sell", label: t.sell, disabled: locked }]}
        onChange={value => { setSide(value as "buy" | "sell"); setError(null); }} />
    </div><Field id="order-qty" label={t.quantity} help={inputSide === "sell" ? t.sellableCount(sellable) : undefined}>
      <Input inputMode="numeric" pattern="[0-9]+" value={inputQuantity} disabled={locked}
        onChange={event => { setQuantity(event.target.value); setError(null); }} />
    </Field><Field id="order-type" label={t.type} help={t.typeHelp}><Input value={t.marketOpen} readOnly /></Field>
    <div className="p-trading__estimate"><dl className="c-kv">
      {[t.estimatePrice, t.estimateAmount, t.estimateFee].map(label => <div key={label}><dt>{label}</dt><dd>{t.unknown}</dd></div>)}
    </dl><p className="c-note u-mt-2">{t.estimateHelp}</p><p className="c-note u-mt-2">{t.fillHelp}</p>
      <p className="c-note">{t.available} {moneyText(portfolio.availableCash)}</p>
    </div>{reference?.estimate && <div className="p-trading__estimate">
      <p className="c-note">{t.referenceEstimate} · {reference.createdClockDate} · {t[reference.side]} {reference.quantity}</p>
      <dl className="c-kv">
        <div><dt>{t.estimatePrice}</dt><dd>{formatDecimal(reference.estimate.price, 4, "$")}</dd></div>
        <div><dt>{t.estimateAmount}</dt><dd>{moneyText(reference.estimate.amount)}</dd></div>
        <div><dt>{t.estimateFee}</dt><dd>{moneyText(reference.estimate.fee)}</dd></div>
      </dl><p className="c-note">{t.referenceHelp}</p>
    </div>}<Button type="submit" variant="primary" loading={busy}>{unresolved ? t.retry : t.submit}</Button>
    {inputSide === "sell" && <p className="c-note">{t.sellHelp}</p>}
  </form>;
}
