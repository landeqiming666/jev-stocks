-- 判定：对一对（逻辑版本，段落）的结论。五个概率是 Jev 对五个 Noul 问题回答"是"的概率（06）。
-- 所有关系（含 none、support）都入库，既是缓存也是评测依据。
CREATE TABLE decision (
  decision_id          VARCHAR PRIMARY KEY,
  thesis_id            VARCHAR NOT NULL,
  thesis_version       INTEGER NOT NULL,
  passage_id           VARCHAR NOT NULL,
  event_id             VARCHAR NOT NULL,     -- 冗余，便于按披露查询
  instrument_id        VARCHAR NOT NULL,     -- 冗余
  relation             VARCHAR NOT NULL,     -- none | support | weaken | overturn | uncertain
  p_relevant           DOUBLE NOT NULL,
  p_against            DOUBLE NOT NULL,
  p_contradicts        DOUBLE NOT NULL,
  p_kill_met           DOUBLE,               -- 没有失效条件时为 NULL
  p_supports           DOUBLE NOT NULL,
  headline             DOUBLE NOT NULL,      -- max(p_against, p_contradicts, coalesce(p_kill_met, 0))
  evidence_kind        VARCHAR,              -- sentence | passage | title；只有进入清单的判定才有
  evidence_start       INTEGER,              -- 证据句在段落文本里的起止字符偏移（kind = sentence 时）
  evidence_end         INTEGER,
  engine               VARCHAR NOT NULL,     -- jevdb | jev_direct
  model_id             VARCHAR NOT NULL,     -- 取自响应里的 model 字段
  question_set_version VARCHAR NOT NULL,
  cache_key            VARCHAR NOT NULL,     -- 见第 4 节
  input_tokens         INTEGER,              -- jev_direct 为实际值；jevdb 为估算值
  tokens_estimated     BOOLEAN NOT NULL DEFAULT FALSE,
  latency_ms           INTEGER,
  content_status       VARCHAR NOT NULL,     -- full_text | title_only
  created_at           TIMESTAMP NOT NULL,
  UNIQUE (cache_key)
);
CREATE INDEX idx_decision_thesis ON decision (thesis_id, created_at);
CREATE INDEX idx_decision_event ON decision (event_id);
