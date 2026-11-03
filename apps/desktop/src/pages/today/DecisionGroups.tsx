import { useState, type ReactNode } from "react";
import type { ActionType, Inbox } from "../../rpc";
import { formatDateTime } from "../../app/format";
import { today } from "../../i18n/zh-CN/today";
import { Button, Icon, MarketBadge, VerdictChip } from "../../components/ui";
import { DecisionCard } from "./DecisionCard";
import { sortDecisions, VISIBLE_CARDS } from "./state";

function Group({ title, children, id }: { title: string; children: ReactNode; id?: string }) {
  const [open, setOpen] = useState(false);
  return <details className="c-group" onToggle={event => setOpen(event.currentTarget.open)}><summary className="c-group__summary" id={id}><Icon name="chevron-right" />{title}</summary>
    <div className="c-group__body" hidden={!open}>{children}</div></details>;
}
export function DecisionGroups({ inbox, onOpen, onAct, onReopen }: {
  inbox: Inbox; onOpen: (id: string) => void; onAct: (id: string, action: ActionType, note?: string) => void; onReopen: (id: string) => void;
}) {
  const items = sortDecisions(inbox.items);
  const cards = (list: typeof items) => <div className="p-today__list">{list.map(item => <DecisionCard key={item.decisionId} item={item} onOpen={onOpen} onAct={onAct} />)}</div>;
  return <>{cards(items.slice(0, VISIBLE_CARDS))}
    {items.length > VISIBLE_CARDS && <Group title={today.remaining(items.length - VISIBLE_CARDS)}>{cards(items.slice(VISIBLE_CARDS))}</Group>}
    {inbox.uncertain.length > 0 && <Group title={today.uncertain(inbox.uncertain.length)}>{cards(sortDecisions(inbox.uncertain))}</Group>}
    {inbox.processed.length > 0 && <Group title={today.processed(inbox.processed.length)} id="today-processed"><ul>
      {inbox.processed.map(item => <li className="c-processed" key={item.decisionId}><div className="c-processed__main">
        <div className="c-processed__line"><MarketBadge market={item.instrument.market} /> <span className="u-mono">{item.instrument.symbol}</span> <VerdictChip kind={item.relation} /> <span className="u-text-2">{item.action && today.actions[item.action.action]}{item.action?.note && ` · ${item.action.note}`}</span></div>
        <div className="u-small u-muted">{item.action && formatDateTime(item.action.actedAt)}</div></div>
        <Button variant="text" onClick={() => onReopen(item.decisionId)} data-action="reopen" data-decision-id={item.decisionId}>{today.actions.reopen}</Button>
      </li>)}</ul></Group>}
  </>;
}
