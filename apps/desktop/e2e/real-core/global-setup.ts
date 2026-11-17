import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { ROOT } from "./fixture";

export default function globalSetup(): void {
  const uv = spawnSync("uv", ["--version"], { encoding: "utf8" });
  if (uv.status !== 0) throw new Error("uv is required for the real-core e2e suite");
  const resources = join(ROOT, "resources");
  if (!existsSync(join(resources, "demo", "manifest.json"))) {
    throw new Error(`missing demo resources at ${resources}`);
  }
  if (!existsSync(join(ROOT, "core", "sentinel", "__main__.py"))) {
    throw new Error("core entry point is missing");
  }
}
