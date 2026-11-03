-- 每日 token 用量，用于每日预算。usage_date 是 UTC 日期，界面显示重置时刻时换算成本地时间。
-- jevdb 引擎的 token 是估算值（字符数 ÷ 3.5），所以单独统计 estimated_tokens。
CREATE TABLE usage_daily (
  usage_date       DATE NOT NULL,
  engine           VARCHAR NOT NULL,
  model_id         VARCHAR NOT NULL,
  input_tokens     BIGINT NOT NULL DEFAULT 0,
  estimated_tokens BIGINT NOT NULL DEFAULT 0,
  requests         INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (usage_date, engine, model_id)
);
