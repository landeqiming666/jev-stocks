import { useRef, useState } from "react";
import { navigate } from "../../app/events";
import type { ActionType, DecisionSummary } from "../../rpc";
import { formatDateTime } from "../../app/format";
import { today } from "../../i18n/zh-CN/today";
import { Button, Card, MarketBadge, Menu, Probability, StatusTag, VerdictChip } from "../../components/ui";

export interface DecisionCardProps {
  item: DecisionSummary; onOpen: (id: string) => void;
  onAct: (id: string, action: ActionType, note?: string) => void;
}
export function DecisionCard({ item, onOpen, onAct }: DecisionCardProps) {
  const [menu, setMenu] = useState(false), trigger = useRef<HTMLButtonElement>(null), card = useRef<HTMLElement>(null);
  const titleId = `t-${item.decisionId}`;
  const prefix = item.contentStatus === "title_only" ? today.titleOnlyPrefix : item.evidence.kind === "passage" ? today.passagePrefix : "";
  return <Card ref={element => {
    card.current = element;
    if (element) { element.classList.add("c-decision"); element.setAttribute("aria-labelledby", titleId); }
  }}>
    <header className="c-decision__head"><MarketBadge market={item.instrument.market} />
      <h3 className="c-decision__title" id={titleId} tabIndex={-1}><span className="u-mono">{item.instrument.symbol}</span> <span className="c-decision__name">{item.instrument.name}</span></h3>
      <VerdictChip kind={item.relation} /><Probability value={item.headline} />
      {item.thesisCurrentVersion > item.thesisVersion && <span className="c-decision__flag"><StatusTag tone="info">{today.thesisUpdated}</StatusTag></span>}</header>
    <p className="c-decision__thesis"><span className="c-decision__label">{today.thesisLabel}</span>{item.thesisStatement}</p>
    <p className="c-decision__evidence"><span className="c-decision__label">{today.evidenceLabel}</span>{prefix}{item.evidence.text}</p>
    <p className="c-decision__meta">{item.event.formType} · {formatDateTime(item.event.publishedAt)} · {item.event.title.replace(/^(?:8-K(?:\/A)?|6-K):\s*/, "")}</p>
    <footer className="c-decision__actions">
      <Button onClick={() => onOpen(item.decisionId)} data-action="open">{today.open}</Button>
      <Button onClick={() => onAct(item.decisionId, "still_valid")} data-action="still_valid">{today.actions.still_valid}</Button>
      <Button onClick={() => navigate("holdings", { thesis: item.thesisId })}>{today.actions.revise}</Button>
      <Button ref={trigger} id={`menu-${item.decisionId}`} variant="icon" icon="more-horizontal" aria-label={today.more}
        aria-haspopup="menu" aria-expanded={menu} data-action="more" onClick={() => setMenu(!menu)} />
      {menu && <Menu triggerRef={trigger} onClose={() => setMenu(false)}
        items={[{ id: "exit_intent", label: today.actions.exit_intent }, { id: "ignore", label: today.actions.ignore }]}
        onSelect={action => onAct(item.decisionId, action as ActionType)} />}
    </footer>
  </Card>;
}
