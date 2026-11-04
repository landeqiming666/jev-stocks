# D-02 测试数据

- `company_tickers_exchange.sample.json`：从主 agent 提供的 SEC 核验快照取前 10 条不含 BRK-B 的真实行，再加入 15 条明确构造的边界行；共 25 行。SEC 来源为 <https://www.sec.gov/files/company_tickers_exchange.json>，快照时间及摘要见生产资源 README。真实公司行不作为真实持仓输入。
- 构造行包含 BRK-B 同规范代码的两个 CIK（1067983、1）、最大合法 CIK 9999999999、OTC/未知交易所、七种非法代码、bool/溢出 CIK。期望计数为 total=25、kept=13、skipped_exchange=2、skipped_symbol=9、duplicates=1。
- `company_tickers_exchange_bad.json`：手写的空响应、缺字段、429 元数据。字段顺序及行形状错误也在参数化测试构造。
- `us_zh.sample.json`：规格样例与中文搜索构造数据，五条。BRK.B 的中文名称和别名未经公开来源核验，不进入生产资源。
