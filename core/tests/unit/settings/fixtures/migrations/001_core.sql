-- 键值设置。值是 JSON 文本。键与默认值见第 5 节。
CREATE TABLE setting (
  key        VARCHAR PRIMARY KEY,
  value_json VARCHAR NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
