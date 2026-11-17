-- 演示数据登记簿。演示数据载入器每插入一行，就在这里记一笔，demo.clear 据此逆序删除。
-- 这是"用户数据禁止物理删除"的例外之一（第 6 节）：只删除登记在册的演示行。
CREATE TABLE demo_row (
  table_name  VARCHAR NOT NULL,
  pk_json     VARCHAR NOT NULL,              -- 主键列的 JSON 对象
  inserted_at TIMESTAMP NOT NULL,
  PRIMARY KEY (table_name, pk_json)
);
