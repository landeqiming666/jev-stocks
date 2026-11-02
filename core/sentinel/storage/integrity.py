"""Read-only association and ledger checks from data model section 7."""

from dataclasses import dataclass

from .db import Database


@dataclass(frozen=True)
class _Rule:
    name: str
    tables: frozenset[str]
    description: str
    sql: str


def _rule(name: str, tables: str, description: str, sql: str) -> _Rule:
    return _Rule(name, frozenset(tables.split()), description, sql)


_RULES = (
    _rule(
        "orphan_thesis_version",
        "thesis_version thesis",
        "逻辑版本缺少所属逻辑",
        """
        SELECT v.thesis_id, v.version FROM thesis_version v
        WHERE NOT EXISTS (SELECT 1 FROM thesis t WHERE t.thesis_id=v.thesis_id)
    """,
    ),
    _rule(
        "thesis_version_gap",
        "thesis thesis_version",
        "逻辑当前版本或版本连续性异常",
        """
        SELECT t.thesis_id, t.current_version FROM thesis t
        LEFT JOIN thesis_version v ON v.thesis_id=t.thesis_id
        GROUP BY t.thesis_id, t.current_version
        HAVING t.current_version IS DISTINCT FROM MAX(v.version)
            OR MIN(v.version) <> 1 OR COUNT(DISTINCT v.version) <> MAX(v.version)
            OR COUNT(v.version) <> COUNT(DISTINCT v.version)
    """,
    ),
    _rule(
        "orphan_decision_thesis",
        "decision thesis_version",
        "判定缺少对应逻辑版本",
        """
        SELECT d.decision_id FROM decision d WHERE NOT EXISTS (
            SELECT 1 FROM thesis_version v
            WHERE v.thesis_id=d.thesis_id AND v.version=d.thesis_version)
    """,
    ),
    _rule(
        "orphan_decision_passage",
        "decision event_passage",
        "判定缺少对应段落",
        """
        SELECT d.decision_id FROM decision d WHERE NOT EXISTS (
            SELECT 1 FROM event_passage p WHERE p.passage_id=d.passage_id)
    """,
    ),
    _rule(
        "orphan_passage",
        "event_passage event_doc",
        "段落缺少所属披露",
        """
        SELECT p.passage_id FROM event_passage p WHERE NOT EXISTS (
            SELECT 1 FROM event_doc e WHERE e.event_id=p.event_id)
    """,
    ),
    _rule(
        "evidence_out_of_range",
        "decision event_passage",
        "证据句偏移超出段落范围",
        """
        SELECT d.decision_id FROM decision d JOIN event_passage p USING(passage_id)
        WHERE d.evidence_kind='sentence' AND (d.evidence_start IS NULL
            OR d.evidence_end IS NULL OR d.evidence_start < 0
            OR d.evidence_start >= d.evidence_end OR d.evidence_end > LENGTH(p.text))
    """,
    ),
    _rule(
        "orphan_action",
        "thesis_action decision",
        "处理记录缺少对应判定",
        """
        SELECT a.action_id FROM thesis_action a WHERE NOT EXISTS (
            SELECT 1 FROM decision d WHERE d.decision_id=a.decision_id)
    """,
    ),
    _rule(
        "batch_run_missing",
        "scan_batch scan_run",
        "扫描批缺少所属运行",
        """
        SELECT b.batch_id FROM scan_batch b WHERE NOT EXISTS (
            SELECT 1 FROM scan_run r WHERE r.run_id=b.run_id)
    """,
    ),
    _rule(
        "order_account_missing",
        "paper_order paper_account",
        "订单缺少所属账户",
        """
        SELECT o.order_id FROM paper_order o WHERE NOT EXISTS (
            SELECT 1 FROM paper_account a WHERE a.account_id=o.account_id)
    """,
    ),
    _rule(
        "fill_without_order",
        "fill paper_order",
        "成交缺少已成交订单",
        """
        SELECT f.fill_id FROM fill f WHERE NOT EXISTS (
            SELECT 1 FROM paper_order o WHERE o.order_id=f.order_id AND o.status='filled')
    """,
    ),
    _rule(
        "filled_order_without_fill",
        "paper_order fill",
        "已成交订单缺少成交记录",
        """
        SELECT o.order_id FROM paper_order o WHERE o.status='filled' AND NOT EXISTS (
            SELECT 1 FROM fill f WHERE f.order_id=o.order_id)
    """,
    ),
    _rule(
        "position_mismatch",
        "position fill paper_order",
        "持仓数量与买卖成交净量不一致",
        """
        WITH net AS (
            SELECT o.account_id, o.instrument_id,
                SUM(CASE o.side WHEN 'buy' THEN f.quantity
                    WHEN 'sell' THEN -f.quantity END) quantity
            FROM fill f JOIN paper_order o USING(order_id)
            GROUP BY o.account_id, o.instrument_id
        )
        SELECT COALESCE(p.account_id,n.account_id), COALESCE(p.instrument_id,n.instrument_id)
        FROM position p FULL OUTER JOIN net n USING(account_id,instrument_id)
        WHERE COALESCE(p.quantity,0) <> COALESCE(n.quantity,0)
    """,
    ),
    _rule(
        "negative_position",
        "position",
        "持仓数量为负",
        """
        SELECT account_id, instrument_id FROM position WHERE quantity < 0
    """,
    ),
    _rule(
        "negative_cash",
        "cash_ledger",
        "账户现金余额为负",
        """
        SELECT account_id FROM cash_ledger GROUP BY account_id
        HAVING COALESCE(SUM(CASE WHEN entry_type IN ('deposit','buy','sell','fee')
            THEN amount END),0) < 0
    """,
    ),
    _rule(
        "reserved_mismatch",
        "cash_ledger paper_order",
        "冻结资金与待处理买单不一致",
        """
        WITH ledger AS (
            SELECT account_id, COALESCE(-SUM(CASE WHEN entry_type IN ('reserve','release')
                THEN amount END),0) reserved FROM cash_ledger GROUP BY account_id
        ), orders AS (
            SELECT account_id, COALESCE(SUM(CASE WHEN status='pending' AND side='buy'
                THEN reserved_cash END),0) reserved FROM paper_order GROUP BY account_id
        )
        SELECT COALESCE(l.account_id,o.account_id)
        FROM ledger l FULL OUTER JOIN orders o USING(account_id)
        WHERE COALESCE(l.reserved,0) <> COALESCE(o.reserved,0)
    """,
    ),
    _rule(
        "equity_mismatch",
        "equity_snapshot",
        "账户权益与现金加持仓市值不一致",
        """
        SELECT account_id, snapshot_date FROM equity_snapshot
        WHERE equity IS DISTINCT FROM cash + positions_value
    """,
    ),
)


def check_integrity(db: Database) -> list[str]:
    errors: list[str] = []
    with db.read() as reader:
        reader.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='main' AND table_catalog=current_database()
        """)
        available = {row[0] for row in reader.fetchall()}
        for rule in _RULES:
            if rule.tables <= available:
                reader.execute(rule.sql)
                for row in reader.fetchall():
                    identifier = ", ".join(str(value) for value in row)
                    errors.append(f"{rule.name}: {rule.description} ({identifier})")
    return sorted(errors)
