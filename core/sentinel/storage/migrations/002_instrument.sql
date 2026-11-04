-- 标的。MVP-0 只有 market = 'us'。来源：SEC company_tickers_exchange.json（见 07）；演示数据为 'demo'。
CREATE TABLE instrument (
  instrument_id VARCHAR PRIMARY KEY,         -- us:AAPL、us:BRK.B
  market        VARCHAR NOT NULL,            -- us（v2：cn、hk）
  symbol        VARCHAR NOT NULL,            -- 规范写法，类股用 .
  exchange      VARCHAR NOT NULL,            -- NASDAQ | NYSE | NYSE American | CBOE
  name          VARCHAR NOT NULL,            -- 英文名
  name_zh       VARCHAR,                     -- 内置别名表里的中文主名，可空
  currency      VARCHAR NOT NULL,            -- USD
  cik           VARCHAR,                     -- SEC CIK，10 位数字字符串（保留前导 0）
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  source        VARCHAR NOT NULL,            -- sec_company_tickers | demo
  updated_at    TIMESTAMP NOT NULL,
  UNIQUE (market, symbol)
);

-- 搜索别名。alias 是已规范化的小写文本（规范化规则见 07 第 4 节）。
CREATE TABLE instrument_alias (
  instrument_id VARCHAR NOT NULL,
  alias         VARCHAR NOT NULL,
  kind          VARCHAR NOT NULL,            -- symbol | name_en | name_zh | alias
  PRIMARY KEY (instrument_id, alias)
);
CREATE INDEX idx_instrument_alias_alias ON instrument_alias (alias);
