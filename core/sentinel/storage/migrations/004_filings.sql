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
