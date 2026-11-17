import { existsSync } from "node:fs";
import { env } from "node:process";

const MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

/** 优先使用显式配置的浏览器；本机没有 Playwright 浏览器时回退到系统 Chrome。 */
export function chromiumExecutable(): string | undefined {
  if (env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) return env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  return existsSync(MAC_CHROME) ? MAC_CHROME : undefined;
}
