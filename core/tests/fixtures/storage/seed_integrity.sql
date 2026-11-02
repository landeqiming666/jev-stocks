-- 合成的完整关联链；每项违规由测试在独立临时库中构造。
INSERT INTO thesis VALUES ('t', 'us:ZZAA', 'active', 1, '2026-11-02', '2026-11-02', NULL);
INSERT INTO thesis_version VALUES ('t', 1, 'Synthetic thesis', NULL, 'hash', '2026-11-02');
INSERT INTO event_doc VALUES ('e', 'us:ZZAA', 'us', '8-K', 'Synthetic filing', '2026-11-02', '2026-11-02', 'https://example.com', NULL, 'full_text', '2026-11-02', 'demo');
INSERT INTO event_passage VALUES ('p', 'e', 0, 0, '合成文本abc', 0, 7, 'hash');
INSERT INTO decision (decision_id, thesis_id, thesis_version, passage_id, event_id, instrument_id, relation, p_relevant, p_against, p_contradicts, p_supports, headline, evidence_kind, evidence_start, evidence_end, engine, model_id, question_set_version, cache_key, content_status, created_at)
VALUES ('d', 't', 1, 'p', 'e', 'us:ZZAA', 'weaken', 1, 0.8, 0.5, 0, 0.8, 'sentence', 0, 3, 'jev_direct', 'jev-1.14.0', 'v1', 'cache', 'full_text', '2026-11-02');
INSERT INTO thesis_action VALUES ('a', 'd', 'ignore', NULL, '2026-11-02');
INSERT INTO scan_run (run_id, trigger, market, status, window_start, window_end, engine, model_id, question_set_version, created_at)
VALUES ('r', 'manual', 'us', 'succeeded', '2026-11-01', '2026-11-02', 'jev_direct', 'jev-1.14.0', 'v1', '2026-11-02');
INSERT INTO scan_batch (batch_id, run_id, instrument_id, event_id, status) VALUES ('b', 'r', 'us:ZZAA', 'e', 'succeeded');
INSERT INTO paper_account VALUES ('acct', 'Synthetic account', 'USD', 100, '2026-11-01', '2026-11-02', TRUE, '2026-11-02', NULL);
INSERT INTO paper_order (order_id, account_id, instrument_id, side, quantity, order_type, status, created_clock_date, reserved_cash, idempotency_key, request_hash, created_at, updated_at)
VALUES ('o', 'acct', 'us:ZZAA', 'buy', 2, 'market_open', 'filled', '2026-11-02', NULL, 'idem1', 'hash', '2026-11-02', '2026-11-02'),
       ('pending', 'acct', 'us:ZZAA', 'buy', 1, 'market_open', 'pending', '2026-11-02', 5, 'idem2', 'hash', '2026-11-02', '2026-11-02');
INSERT INTO fill VALUES ('f', 'o', '2026-11-02', 10, 2, 20, 0, 0, '2026-11-02');
INSERT INTO position VALUES ('acct', 'us:ZZAA', 2, 10, '2026-11-02');
INSERT INTO cash_ledger VALUES ('cash', 'acct', '2026-11-02', 'deposit', 100, NULL, '2026-11-02'),
                               ('reserve', 'acct', '2026-11-02', 'reserve', -5, 'pending', '2026-11-02');
INSERT INTO equity_snapshot VALUES ('acct', '2026-11-02', 100, 20, 120);
