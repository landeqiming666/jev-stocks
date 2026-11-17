export interface DemoStep {
  readonly at: string;
  readonly seconds: number;
  readonly page: string;
  readonly action: string;
  readonly expected: string;
  readonly fallback: string;
}

/** 5 分钟演示脚本；页面与数据均来自离线演示集（虚构公司）。 */
export const DEMO_SCRIPT: readonly DemoStep[] = [
  {
    at: "0:00–0:25",
    seconds: 25,
    page: "启动",
    action: "启动应用，等待核心就绪",
    expected: "标题“投资逻辑哨兵”，顶栏显示“演示数据 · 离线 · 引擎未配置”",
    fallback: "15 秒未就绪则重启一次；仍失败只说明已知缺陷，不继续",
  },
  {
    at: "0:25–1:05",
    seconds: 40,
    page: "今日",
    action: "打开今日页",
    expected: "标题“今天有 2 件事需要你看一眼”；ZZAR 推翻 0.93、ZZCL 削弱 0.78；“系统拿不准的 1 条”折叠",
    fallback: "页面异常则只展示数据目录中的演示清单，不手工造卡",
  },
  {
    at: "1:05–1:45",
    seconds: 40,
    page: "今日 · 证据",
    action: "点“查看原文”打开证据抽屉",
    expected: "高亮 4.5% 减持句；显示引擎 JEVDB、模型 jev-1.14.0 与问题集版本",
    fallback: "抓取失败时显示已存句子，并明确“演示数据预置”",
  },
  {
    at: "1:45–2:15",
    seconds: 30,
    page: "今日 · 处理",
    action: "点“仍然成立”，再展开已处理并“重新打开”",
    expected: "待处理 2 → 1 → 2；动作写入时间线",
    fallback: "写入失败时展示错误编号，不继续交易步骤",
  },
  {
    at: "2:15–2:55",
    seconds: 40,
    page: "持仓",
    action: "展开 ZZAR 的两条逻辑与失效条件",
    expected: "5 个标的、6 条逻辑；中文名与英文名同时可见",
    fallback: "编辑器异常时只读展示，不现场改数据库",
  },
  {
    at: "2:55–3:25",
    seconds: 30,
    page: "扫描",
    action: "查看扫描历史与预算",
    expected: "1 条预置运行、6 份披露、预算与引擎信息；说明这是离线演示数据",
    fallback: "历史为空则展示 E-01 固定计数，不声称刚扫描成功",
  },
  {
    at: "3:25–4:05",
    seconds: 40,
    page: "交易",
    action: "点“下一交易日”",
    expected: "回放日期 2026-10-29 → 2026-10-30；1 笔待成交变为成交",
    fallback: "推进失败则展示拒单原因与组合，不伪造成交",
  },
  {
    at: "4:05–4:35",
    seconds: 30,
    page: "风险",
    action: "查看相关系数、波动率与 SVD",
    expected: "3 只持仓、252 个共同交易日；对角线为 1.00",
    fallback: "样本不足则展示页面真实提示并跳过数字讲解",
  },
  {
    at: "4:35–4:55",
    seconds: 20,
    page: "设置",
    action: "展示“已载入演示数据”与外联域名",
    expected: "密钥只显示“已保存/未保存”，不显示明文；列出外联域名",
    fallback: "密钥未配置则演示“去设置”的阻断，不输入真实密钥",
  },
  {
    at: "4:55–5:00",
    seconds: 5,
    page: "设置 · 演示数据",
    action: "点“清除演示数据”，确认框出现后取消",
    expected: "确认框可见；取消后数据保持",
    fallback: "按钮异常则命令行演示 --clear，并说明是清理动作",
  },
];

export const DEMO_SECONDS = DEMO_SCRIPT.reduce((total, step) => total + step.seconds, 0);
