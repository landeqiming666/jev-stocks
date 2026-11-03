-- 风险计算的审计记录：输入、参数、结果摘要。便于复现与排错。
CREATE TABLE risk_run (
  run_id           VARCHAR PRIMARY KEY,
  computed_at      TIMESTAMP NOT NULL,
  scope            VARCHAR NOT NULL,         -- holdings
  window_label     VARCHAR NOT NULL,         -- 6M | 1Y | 3Y
  currency         VARCHAR NOT NULL,         -- USD
  observations     INTEGER NOT NULL,
  instrument_ids   VARCHAR NOT NULL,         -- JSON 数组
  params_json      VARCHAR NOT NULL,         -- shrinkage_alpha、price_basis、code_version 等
  result_json      VARCHAR NOT NULL          -- 与 risk.compute 的结果一致
);
