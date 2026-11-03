import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { defineConfig } from "vitest/config";

const desktopRoot = fileURLToPath(new URL("../../../", import.meta.url));
const productionRef = "5447acd0493c56bbee1222abb506a31b03fb27b0";
const sharedPaths = ["src/app/Application.tsx", "src/shell/AppShell.tsx", "src/router/RouterView.tsx", "src/components/feedback/OfflineBanner.tsx"];
// 共享前置有冲突时只读编译已批准生产源码；主树可直接测当前 checkout，不改共享文件。
const sources = process.env.U02_USE_CHECKOUT_APPLICATION === "1" ? new Map<string, string>() : new Map(sharedPaths.map(path => [
  resolve(desktopRoot, path), execFileSync("git", ["show", `${productionRef}:apps/desktop/${path}`], {
    cwd: resolve(desktopRoot, "../.."), encoding: "utf8",
  }),
]));
export default defineConfig({
  root: desktopRoot,
  resolve: { alias: { "@": resolve(desktopRoot, "src") } },
  plugins: [{ name: "u02-reviewed-application", enforce: "pre", load(id) { return sources.get(id.split("?")[0]!); } }],
  test: { environment: "jsdom", include: ["src/pages/today/ApplicationComposition.spec.tsx"] },
});
