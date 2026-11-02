# 第三方许可证清单

- 生成日期：2026-11-02
- 版本来源：`core/uv.lock`、`apps/desktop/pnpm-lock.yaml`、`apps/desktop/src-tauri/Cargo.lock`
- 许可证来源：Python 用 `importlib.metadata` 读取已安装包元数据；前端读 `node_modules/<包>/package.json`；Rust 用 `cargo metadata`。没有凭记忆填写。
- 本表只列 [02-技术架构.md](docs/02-技术架构.md) 第 4 节白名单里的直接依赖，不列传递依赖。

## Python（`core/pyproject.toml`）

| 包 | 版本 | 许可证 |
|---|---|---|
| duckdb | 1.4.3 | MIT |
| typesafe-sdk | 0.7.5 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| selectolax | 1.0.2 | MIT |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| keyring | 25.7.0 | MIT |
| pydantic | 2.14.2 | MIT |
| tzdata | 2026.6 | Apache-2.0 |
| hatchling（构建后端） | 1.33.0 | MIT |
| pytest | 9.2.0 | MIT |
| pytest-timeout | 2.4.0 | MIT |
| jsonschema | 4.26.0 | MIT |
| ruff | 0.17.3 | MIT |
| mypy | 2.4.1 | MIT |

## 前端（`apps/desktop/package.json`）

| 包 | 版本 | 许可证 |
|---|---|---|
| react | 19.3.1 | MIT |
| react-dom | 19.3.1 | MIT |
| zustand | 5.0.16 | MIT |
| @tauri-apps/api | 2.12.4 | Apache-2.0 OR MIT |
| vite | 8.3.5 | MIT |
| @vitejs/plugin-react | 6.1.2 | MIT |
| typescript | 6.0.3 | Apache-2.0 |
| @tauri-apps/cli | 2.12.4 | Apache-2.0 OR MIT |
| vitest | 5.0.5 | MIT |
| @testing-library/react | 16.3.3 | MIT |
| jsdom | 30.1.3 | MIT |
| @playwright/test | 1.64.1 | Apache-2.0 |
| eslint | 10.14.0 | MIT |
| @eslint/js | 10.0.1 | MIT |
| typescript-eslint | 8.72.1 | MIT |
| eslint-plugin-react-hooks | 7.1.1 | MIT |
| @types/react | 19.3.0 | MIT |
| @types/react-dom | 19.3.0 | MIT |
| @types/node | 26.6.6 | MIT |

## Rust（`apps/desktop/src-tauri/Cargo.toml`）

| crate | 版本 | 许可证 |
|---|---|---|
| tauri | 2.12.5 | Apache-2.0 OR MIT |
| tauri-build | 2.7.4 | Apache-2.0 OR MIT |
| tauri-plugin-single-instance | 2.5.5 | Apache-2.0 OR MIT |
| serde | 1.0.229 | MIT OR Apache-2.0 |
| serde_json | 1.0.154 | MIT OR Apache-2.0 |

## 待核实项

- `TODO-VERIFY(WP-00)`：已核实。`typesafe-sdk==0.7.5` 在 Python 3.12.13（macOS arm64）下可安装、可导入，许可证 MIT。
- 无 `UNKNOWN` 许可证项。
