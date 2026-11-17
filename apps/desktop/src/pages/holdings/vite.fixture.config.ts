import { fileURLToPath } from "node:url";
import { defineConfig, mergeConfig } from "vite";
import base from "../../../vite.config";
// 独立原型只读对照；此配置不进入生产 build。
export default mergeConfig(base, defineConfig({ server: {
  port: 1463, strictPort: true, host: "127.0.0.1",
  fs: { allow: [fileURLToPath(new URL("../../../../../", import.meta.url))] },
} }));
