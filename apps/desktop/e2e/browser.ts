import { existsSync } from "node:fs";
import { env } from "node:process";
import { join } from "node:path";

const MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

/** 优先使用显式配置的浏览器；本机没有 Playwright 浏览器时回退到系统 Chrome。 */
export function chromiumExecutable(): string | undefined {
  if (env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) return env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  const candidates = [
    MAC_CHROME,
    ...[env["ProgramFiles(x86)"], env.ProgramFiles, env.LOCALAPPDATA]
      .filter((directory): directory is string => Boolean(directory))
      .map(directory => join(directory, "Microsoft", "Edge", "Application", "msedge.exe")),
  ];
  return candidates.find(path => existsSync(path));
}
