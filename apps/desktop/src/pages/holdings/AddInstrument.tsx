import { useEffect, useRef, useState, type RefObject } from "react";
import { useAppStore } from "../../app/store";
import { SearchInput, StatusTag } from "../../components/ui";
import { holdings as text } from "../../i18n/zh-CN/holdings";
import { RpcError } from "../../rpc";
import type { Instrument } from "../../rpc/generated/types";
import { errorText } from "./use-resource";
import { countText, trimText } from "./validation";

export const SEARCH_DEBOUNCE_MS = 300;
export const SEARCH_LIMIT = 10;
export function AddInstrument({ existing, disabled, onSelect, inputRef }: {
  existing: string[]; disabled: boolean; onSelect: (instrument: Instrument) => void;
  inputRef: RefObject<HTMLInputElement | null>;
}) {
  const client = useAppStore(s => s.client);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<Instrument[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(-1);
  const sequence = useRef(0);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const id = ++sequence.current, controller = new AbortController(), search = trimText(query);
    setItems([]); setError(null); setActive(-1); setLoading(!!search);
    if (!search || countText(search) > 64) { setLoading(false); if (search) setError(text.searchLong); return; }
    const timer = setTimeout(() => {
      if (!client) { setError(text.disconnected); setLoading(false); return; }
      void client.call("instruments.search", { query: search, limit: SEARCH_LIMIT }, { signal: controller.signal })
        .then(result => {
          if (sequence.current !== id || controller.signal.aborted) return;
          setItems(result.items.filter(i => i.market === "us").slice(0, SEARCH_LIMIT));
        }).catch(error => {
          if (sequence.current !== id || controller.signal.aborted) return;
          setError(error instanceof RpcError && error.code === "CONFIG_REQUIRED" ? text.needEmail : errorText(error));
        }).finally(() => { if (sequence.current === id && !controller.signal.aborted) setLoading(false); });
    }, SEARCH_DEBOUNCE_MS);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, client]);
  useEffect(() => {
    function outside(event: PointerEvent) { if (!root.current?.contains(event.target as Node)) setOpen(false); }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, []);
  function select(item: Instrument) {
    if (disabled || existing.includes(item.instrumentId)) return;
    sequence.current++; setOpen(false); setQuery(""); onSelect(item);
  }
  function move(direction: number) {
    const available = items.map((item, index) => existing.includes(item.instrumentId) ? -1 : index).filter(i => i >= 0);
    if (!available.length) return;
    const position = available.indexOf(active);
    setActive(position < 0 ? available[direction > 0 ? 0 : available.length - 1]! : available[(position + direction + available.length) % available.length]!);
    setOpen(true);
  }
  return <div ref={root} className="p-holdings__combobox" onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false); }}>
    <SearchInput ref={inputRef} id="add-instrument" aria-label={text.add} placeholder={text.search} value={query}
      disabled={disabled} expanded={open && !!query} aria-controls="add-instrument-list"
      aria-activedescendant={open && active >= 0 ? `holding-option-${active}` : undefined}
      onFocus={() => { if (query) setOpen(true); }}
      onChange={e => { sequence.current++; setQuery(e.target.value); setOpen(true); setItems([]); }}
      onKeyDown={e => {
        if (e.nativeEvent.isComposing) return;
        if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); move(e.key === "ArrowDown" ? 1 : -1); }
        if (e.key === "Enter" && active >= 0 && items[active]) { e.preventDefault(); select(items[active]); }
        if (e.key === "Escape") { e.preventDefault(); setOpen(false); }
      }} />
    {open && query && <div className="p-holdings__search-list" id="add-instrument-list" role="listbox" aria-label={text.searchResults} aria-busy={loading}>
      {loading || error || !items.length ? <div className="p-holdings__search-empty" role="status">{loading ? text.loading : error ?? text.searchEmpty}</div> :
        items.map((item, index) => <div key={item.instrumentId} id={`holding-option-${index}`} role="option"
          aria-selected={active === index} aria-disabled={existing.includes(item.instrumentId)}
          className={`p-holdings__option${active === index ? " is-active" : ""}`}
          onPointerDown={e => e.preventDefault()} onClick={() => select(item)}>
          <strong className="u-mono">{item.symbol}</strong><span className="u-grow u-truncate">{item.name} · {item.nameZh}</span>
          <span className="u-small u-muted">{item.exchange}</span>{existing.includes(item.instrumentId) && <StatusTag tone="none">{text.added}</StatusTag>}
        </div>)}
    </div>}
  </div>;
}
