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
