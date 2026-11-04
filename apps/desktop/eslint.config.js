import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default [
  {
    ignores: [
      "dist/**",
      "node_modules/**",
      "src-tauri/target/**",
      "playwright-report/**",
      "test-results/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: {
      "react-hooks": reactHooks,
    },
    languageOptions: {
      globals: {
        console: "readonly",
        document: "readonly",
        navigator: "readonly",
        window: "readonly",
      },
    },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "error",
      "no-restricted-syntax": [
        "error",
        {
          selector: "Literal[value=/^#[0-9a-fA-F]{3,8}$/]",
          message: "禁止内联颜色，使用设计令牌（ADR-010）",
        },
      ],
    },
  },
  {
    // Playwright 的 fixture 形参名 `use` 不是 React Hook。
    files: ["e2e/**/*.ts"],
    rules: {
      "react-hooks/rules-of-hooks": "off",
      "react-hooks/exhaustive-deps": "off",
    },
  },
];
