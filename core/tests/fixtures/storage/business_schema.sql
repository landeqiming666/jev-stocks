-- 键值设置。值是 JSON 文本。键与默认值见第 5 节。
CREATE TABLE setting (
  key        VARCHAR PRIMARY KEY,
  value_json VARCHAR NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

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

-- 用户登记的真实持仓。quantity = 0 表示"只关注"。重新添加已归档的标的时，清空 archived_at 并更新其余列。
CREATE TABLE holding (
  holding_id    VARCHAR PRIMARY KEY,
  instrument_id VARCHAR NOT NULL UNIQUE,
  quantity      DECIMAL(18,4) NOT NULL DEFAULT 0,
  avg_cost      DECIMAL(18,4),               -- 可空
  note          VARCHAR,                     -- ≤ 200 字
  created_at    TIMESTAMP NOT NULL,
  updated_at    TIMESTAMP NOT NULL,
  archived_at   TIMESTAMP
);

-- 投资逻辑。具体文字在 thesis_version 里；这里只放身份、状态和乐观锁用的当前版本号。
CREATE TABLE thesis (
  thesis_id       VARCHAR PRIMARY KEY,
  instrument_id   VARCHAR NOT NULL,
  status          VARCHAR NOT NULL,          -- active | archived
  current_version INTEGER NOT NULL,          -- 乐观锁：UPDATE ... WHERE current_version = :expected
  created_at      TIMESTAMP NOT NULL,
  updated_at      TIMESTAMP NOT NULL,
  archived_at     TIMESTAMP
);
CREATE INDEX idx_thesis_instrument ON thesis (instrument_id, status);

-- 逻辑的每个版本，不可变。
CREATE TABLE thesis_version (
  thesis_id      VARCHAR NOT NULL,
  version        INTEGER NOT NULL,           -- 从 1 开始，每次编辑 +1
  statement      VARCHAR NOT NULL,           -- 1..500 字（Unicode 码点，去首尾空白后计数）
  kill_condition VARCHAR,                    -- ≤ 300 字，可空
  content_hash   VARCHAR NOT NULL,           -- 见第 4 节，判定缓存键的一部分
  created_at     TIMESTAMP NOT NULL,
  PRIMARY KEY (thesis_id, version)
);

-- 一次监管披露（一份 8-K / 8-K/A / 6-K）。
CREATE TABLE event_doc (
  event_id       VARCHAR PRIMARY KEY,        -- us:<accession>，保留连字符
  instrument_id  VARCHAR NOT NULL,
  market         VARCHAR NOT NULL,
  form_type      VARCHAR NOT NULL,           -- 8-K | 8-K/A | 6-K（v1 增加 10-Q 10-K 20-F 4）
  title          VARCHAR NOT NULL,           -- 由表单类型 + Item 名称或首行标题拼成，见 07 第 5 节
  published_at   TIMESTAMP NOT NULL,         -- SEC acceptanceDateTime，UTC
  filing_date    DATE NOT NULL,              -- SEC filingDate
  url            VARCHAR NOT NULL,           -- 主文档地址，仅 https
  items          VARCHAR,                    -- 8-K 的 Item 编号，逗号分隔，如 "2.02,9.01"
  content_status VARCHAR NOT NULL,           -- full_text | title_only | fetch_failed
  fetched_at     TIMESTAMP NOT NULL,
  source         VARCHAR NOT NULL            -- sec_edgar | demo
);
CREATE INDEX idx_event_doc_instrument ON event_doc (instrument_id, published_at);

-- 披露内的文件：主文档与 EX-99.* 附件。
CREATE TABLE event_file (
  event_id    VARCHAR NOT NULL,
  seq         INTEGER NOT NULL,              -- 0 = 主文档；1.. = 附件
  file_name   VARCHAR NOT NULL,
  doc_type    VARCHAR NOT NULL,              -- 8-K | 6-K | EX-99.1 | EX-99.2 ...
  url         VARCHAR NOT NULL,
  text_status VARCHAR NOT NULL,              -- extracted | empty | failed | skipped
  text        VARCHAR,                       -- 清洗后的纯文本
  char_count  INTEGER,
  PRIMARY KEY (event_id, seq)
);

-- 段落：判定的最小文本单位。file_seq = -1 表示"标题段落"（正文缺失时只有标题可判）。
CREATE TABLE event_passage (
  passage_id   VARCHAR PRIMARY KEY,          -- 见第 4 节
  event_id     VARCHAR NOT NULL,
  file_seq     INTEGER NOT NULL,
  seq          INTEGER NOT NULL,             -- 文件内的段落序号，从 0 开始
  text         VARCHAR NOT NULL,             -- ≤ 1200 字符
  start_offset INTEGER NOT NULL,             -- 在文件文本里的字符偏移
  end_offset   INTEGER NOT NULL,
  content_hash VARCHAR NOT NULL,             -- 见第 4 节
  UNIQUE (event_id, file_seq, seq)
);

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

-- 用户对判定的处理记录。只追加，不修改。清单状态由"最新一条记录"决定。
CREATE TABLE thesis_action (
  action_id   VARCHAR PRIMARY KEY,           -- ULID，同一时刻按它排序
  decision_id VARCHAR NOT NULL,
  action      VARCHAR NOT NULL,              -- still_valid | revise | exit_intent | ignore | reopen
  note        VARCHAR,                       -- ≤ 200 字
  created_at  TIMESTAMP NOT NULL
);
CREATE INDEX idx_action_decision ON thesis_action (decision_id, created_at);

-- 每条判定的最新处理记录。没有记录的判定不在视图里。
CREATE VIEW v_last_action AS
SELECT decision_id, action, note, created_at AS acted_at
FROM thesis_action
QUALIFY ROW_NUMBER() OVER (PARTITION BY decision_id ORDER BY created_at DESC, action_id DESC) = 1;

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

-- 演示数据登记簿。演示数据载入器每插入一行，就在这里记一笔，demo.clear 据此逆序删除。
-- 这是"用户数据禁止物理删除"的例外之一（第 6 节）：只删除登记在册的演示行。
CREATE TABLE demo_row (
  table_name  VARCHAR NOT NULL,
  pk_json     VARCHAR NOT NULL,              -- 主键列的 JSON 对象
  inserted_at TIMESTAMP NOT NULL,
  PRIMARY KEY (table_name, pk_json)
);
