import { defineConfig } from "@playwright/test";
import base from "./playwright.config";
export default defineConfig({ ...base, testMatch: "pixel.spec.ts", outputDir: "../../../test-results/u03/pixel-output",
  snapshotPathTemplate: "{testDir}/../../../test-results/u03/pixel-baseline/{arg}{ext}" });
