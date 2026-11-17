-- 一次扫描运行。统计列在运行过程中由扫描线程逐批累加。
CREATE TABLE scan_run (
  run_id               VARCHAR PRIMARY KEY,
  trigger              VARCHAR NOT NULL,     -- manual | schedule（v1）
  market               VARCHAR NOT NULL,
  status               VARCHAR NOT NULL,     -- queued | running | succeeded | partial | failed | cancelled | interrupted
  window_start         TIMESTAMP NOT NULL,
  window_end           TIMESTAMP NOT NULL,
  engine               VARCHAR NOT NULL,
  model_id             VARCHAR NOT NULL,
  question_set_version VARCHAR NOT NULL,
  instruments          INTEGER NOT NULL DEFAULT 0,   -- 实际扫描的标的数
  skipped_no_thesis    INTEGER NOT NULL DEFAULT 0,   -- 因没有有效逻辑被跳过的标的数
  filings              INTEGER NOT NULL DEFAULT 0,
  passages             INTEGER NOT NULL DEFAULT 0,
  decisions            INTEGER NOT NULL DEFAULT 0,   -- 本次新产生的判定数
  cached_decisions     INTEGER NOT NULL DEFAULT 0,   -- 命中缓存、未发请求的判定数
  requests             INTEGER NOT NULL DEFAULT 0,
  input_tokens         BIGINT NOT NULL DEFAULT 0,
  est_cost_usd         DECIMAL(18,6) NOT NULL DEFAULT 0,
  duration_ms          INTEGER,
  error_code           VARCHAR,
  error_message        VARCHAR,
  started_at           TIMESTAMP,
  finished_at          TIMESTAMP,
  created_at           TIMESTAMP NOT NULL
);
CREATE INDEX idx_scan_run_created ON scan_run (market, created_at);

-- 扫描批：一个标的 × 一份披露。一批失败不影响其他批。
CREATE TABLE scan_batch (
  batch_id      VARCHAR PRIMARY KEY,
  run_id        VARCHAR NOT NULL,
  instrument_id VARCHAR NOT NULL,
  event_id      VARCHAR NOT NULL,
  status        VARCHAR NOT NULL,            -- pending | succeeded | failed | cancelled
  attempts      INTEGER NOT NULL DEFAULT 0,
  passages      INTEGER NOT NULL DEFAULT 0,
  decisions     INTEGER NOT NULL DEFAULT 0,
  input_tokens  INTEGER NOT NULL DEFAULT 0,
  error_code    VARCHAR,
  error_message VARCHAR,
  started_at    TIMESTAMP,
  finished_at   TIMESTAMP,
  UNIQUE (run_id, instrument_id, event_id)
);

-- 水位线：这个时间点之前的披露列表都已成功获取（ADR-012）。
CREATE TABLE watermark (
  market        VARCHAR PRIMARY KEY,
  covered_until TIMESTAMP NOT NULL,
  updated_at    TIMESTAMP NOT NULL
);
