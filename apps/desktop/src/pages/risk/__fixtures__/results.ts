import type { RiskResult } from "../../../rpc";
import okWire from "./ok.json";
import singleWire from "./single.json";

export const ok = okWire as RiskResult;
export const single = singleWire as RiskResult;
export function resultFor(state: string, window: RiskResult["window"]["label"] = "1Y"): RiskResult {
  const result = structuredClone(state === "single" ? single : ok);
  result.window.label = window;
  if (state === "three-year" || window === "3Y") result.warnings.push("数据不足三年，实际从 2025-10-30 起");
  if (state === "unadjusted") result.warnings.push("价格未复权", "ZZCL 最新行情超过 3 个交易日未更新");
  if (state === "singular") {
    result.conditionNumberRaw = null;
    result.warnings.push("协方差矩阵接近奇异");
  }
  if (state === "null" || state === "zero") {
    result.correlation.matrix = result.correlation.matrix.map((row, i) => row.map((value, j) =>
      state === "zero" || i === 2 || j === 2 ? null : value));
    result.warnings.push("部分资产无波动，保留原权重；相关系数不可定义");
  }
  if (state === "zero") {
    result.annualizedVol = 0;
    result.maxDrawdown = 0;
    result.svd = { explained: [], loadings: [] };
    result.conditionNumberRaw = null;
    result.conditionNumberShrunk = null;
    result.warnings.push("资产无波动，标准化主成分分析不可定义");
  }
  return result;
}
