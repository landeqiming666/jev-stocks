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
