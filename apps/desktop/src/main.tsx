import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { Application } from "./app/Application";
import { common } from "./i18n/zh-CN";
import { feedbackRootOptions } from "./lib/errors";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/layout.css";
import "./styles/platform-macos.css";
import "./styles/platform-windows.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error(common.rootMissing);
}

document.documentElement.dataset.platform ??= "macos";
createRoot(container, feedbackRootOptions).render(
  <StrictMode>
    <Application />
  </StrictMode>,
);
