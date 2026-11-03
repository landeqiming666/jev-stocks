-- 日线行情。OHLC 与成交量来自行情源（见 07）。adj_close 缺失时风险计算退回 close 并给出警告。
CREATE TABLE price_daily (
  instrument_id VARCHAR NOT NULL,
  trade_date    DATE NOT NULL,
  open          DOUBLE,
  high          DOUBLE,
  low           DOUBLE,
  close         DOUBLE,
  adj_close     DOUBLE,
  volume        BIGINT,
  source        VARCHAR NOT NULL,            -- 行情源标识 | demo
  fetched_at    TIMESTAMP NOT NULL,
  PRIMARY KEY (instrument_id, trade_date)
);
