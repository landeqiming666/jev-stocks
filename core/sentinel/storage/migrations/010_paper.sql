-- 模拟账户。clock_date 是回放时钟（ADR-013）：撮合与估值只读 trade_date <= clock_date 的行情。
CREATE TABLE paper_account (
  account_id    VARCHAR PRIMARY KEY,
  name          VARCHAR NOT NULL UNIQUE,     -- ≤ 30 字
  base_currency VARCHAR NOT NULL,            -- USD
  initial_cash  DECIMAL(18,4) NOT NULL,
  start_date    DATE NOT NULL,
  clock_date    DATE NOT NULL,
  is_demo       BOOLEAN NOT NULL DEFAULT FALSE,
  created_at    TIMESTAMP NOT NULL,
  archived_at   TIMESTAMP
);

-- 现金流水，只追加。余额由流水汇总得出，不单独存储，避免出现两个"真相"。
--   现金      = SUM(amount) 其中 entry_type IN ('deposit','buy','sell','fee')
--   冻结资金  = -SUM(amount) 其中 entry_type IN ('reserve','release')
--   可用现金  = 现金 - 冻结资金
CREATE TABLE cash_ledger (
  entry_id   VARCHAR PRIMARY KEY,
  account_id VARCHAR NOT NULL,
  entry_date DATE NOT NULL,                  -- 模拟日期
  entry_type VARCHAR NOT NULL,               -- deposit | buy | sell | fee | reserve | release
  amount     DECIMAL(18,4) NOT NULL,         -- 正数增加，负数减少
  ref_id     VARCHAR,                        -- order_id 或 fill_id
  created_at TIMESTAMP NOT NULL
);
CREATE INDEX idx_cash_ledger_account ON cash_ledger (account_id, entry_date);

CREATE TABLE paper_order (
  order_id           VARCHAR PRIMARY KEY,
  account_id         VARCHAR NOT NULL,
  instrument_id      VARCHAR NOT NULL,
  side               VARCHAR NOT NULL,       -- buy | sell
  quantity           INTEGER NOT NULL,
  order_type         VARCHAR NOT NULL,       -- market_open（v1 增加 limit）
  status             VARCHAR NOT NULL,       -- pending | filled | rejected | cancelled
  reject_code        VARCHAR,                -- 见 08 第 4 节的拒单原因码
  reject_message     VARCHAR,
  created_clock_date DATE NOT NULL,          -- 下单时账户的模拟日期
  estimate_price     DECIMAL(18,6),          -- 下单时的估算价 = 收盘价 × (1 + 滑点)
  reserved_cash      DECIMAL(18,4),          -- 买单冻结的资金，成交/取消/拒绝后清空
  idempotency_key    VARCHAR NOT NULL UNIQUE,
  request_hash       VARCHAR NOT NULL,       -- 其余下单参数的摘要，用于识别"同键不同参数"
  created_at         TIMESTAMP NOT NULL,
  updated_at         TIMESTAMP NOT NULL
);
CREATE INDEX idx_paper_order_account ON paper_order (account_id, status, created_at);

CREATE TABLE fill (
  fill_id      VARCHAR PRIMARY KEY,
  order_id     VARCHAR NOT NULL,
  filled_on    DATE NOT NULL,
  price        DECIMAL(18,6) NOT NULL,       -- 开盘价 × (1 ± 滑点)
  quantity     INTEGER NOT NULL,
  amount       DECIMAL(18,4) NOT NULL,       -- price × quantity
  fee          DECIMAL(18,4) NOT NULL,
  slippage_bps DOUBLE NOT NULL,
  created_at   TIMESTAMP NOT NULL
);

CREATE TABLE position (
  account_id    VARCHAR NOT NULL,
  instrument_id VARCHAR NOT NULL,
  quantity      INTEGER NOT NULL,            -- 清仓后保留 0，界面隐藏
  avg_cost      DECIMAL(18,6) NOT NULL,      -- 含买入费用的加权平均成本
  updated_at    TIMESTAMP NOT NULL,
  PRIMARY KEY (account_id, instrument_id)
);

-- 每个模拟日收盘后的权益快照，用于权益曲线（v1）和一致性检查。
CREATE TABLE equity_snapshot (
  account_id      VARCHAR NOT NULL,
  snapshot_date   DATE NOT NULL,
  cash            DECIMAL(18,4) NOT NULL,
  positions_value DECIMAL(18,4) NOT NULL,
  equity          DECIMAL(18,4) NOT NULL,
  PRIMARY KEY (account_id, snapshot_date)
);
