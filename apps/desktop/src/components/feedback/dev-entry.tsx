import { StrictMode, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { startApp } from "../../app/bootstrap";
import { notifyToast } from "../../app/events";
import { useAppStore } from "../../app/store";
import { feedback } from "../../i18n/zh-CN/feedback";
import type { CoreStatusListener } from "../../lib/core-status";
import { getRpcClient } from "../../rpc";
import { PageFrame } from "../../shell/PageFrame";
import { NavRail } from "../../shell/NavRail";
import { TopBar } from "../../shell/TopBar";
import { StatusBar } from "../../shell/StatusBar";
import { AppShell } from "../../shell/AppShell";
import { Banner, Button, Card, Drawer, Menu, Modal, StatusTag } from "../ui";
import { ErrorBoundary, FeedbackHost, feedbackRootOptions } from "./index";
import "../../styles/tokens.css";
import "../../styles/base.css";
import "../../styles/layout.css";
import "../../styles/platform-macos.css";
import "./dev-gallery.css";

if (!import.meta.env.DEV || import.meta.env.VITE_RPC !== "mock") throw new Error("Mock development entry required");
const stop = startApp(getRpcClient());
import.meta.hot?.dispose(stop);
const statusListeners = new Set<(payload: unknown) => void>();
const listener: CoreStatusListener = async handler => { statusListeners.add(handler); return () => { statusListeners.delete(handler); }; };
const g = feedback.gallery;
function Broken({ broken }: { broken: boolean }) {
  if (broken) throw new Error("test-key-do-not-use private-thesis private-holding 1234.5600");
  return <Banner tone="info" text={g.stable} />;
}
function Gallery() {
  const [broken, setBroken] = useState(false), [duplicate, setDuplicate] = useState(false);
  const [drawer, setDrawer] = useState(false), [modal, setModal] = useState(false), [menu, setMenu] = useState(false);
  const [overlay, setOverlay] = useState(window.innerWidth < 1200);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 1199px)");
    const change = () => setOverlay(media.matches);
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  const trigger = useRef<HTMLButtonElement>(null);
  const ready = useAppStore(state => state.bootstrap.status === "ready");
  const toggleOffline = () => useAppStore.setState(state => ({ bootstrap: { ...state.bootstrap,
    value: state.bootstrap.value && { ...state.bootstrap.value, offline: !state.bootstrap.value.offline } } }));
  const status = (state: string) => { for (const fn of [...statusListeners]) fn({ state, attempt: state === "failed" ? 3 : 0 }); };
  const drawerContent = <Drawer open={drawer} overlay={overlay} titleId="feedback-drawer-title" onClose={() => setDrawer(false)}>
    <div className="c-drawer__head"><h2 id="feedback-drawer-title">{g.drawer}</h2></div>
    <div className="c-drawer__body"><Button onClick={() => setModal(true)}>{g.modal}</Button></div>
  </Drawer>;
  const content = <FeedbackHost coreStatusListener={listener}>
      <PageFrame asideOpen={drawer && !overlay} aside={overlay ? undefined : drawerContent} asideLabel={g.drawer}>
      <header className="u-feedback-header"><div><p className="c-note">{g.subtitle}</p><h1 className="u-h1">{g.title}</h1></div>
        <StatusTag tone="none">{g.fixture}</StatusTag></header>
      <div className="u-feedback-controls">
        <Button onClick={() => notifyToast("success", g.saved)}>{g.success}</Button>
        <Button onClick={() => notifyToast("error", g.failed)}>{g.error}</Button>
        <Button onClick={toggleOffline}>{g.offline}</Button>
        <Button onClick={() => setBroken(true)}>{g.crash}</Button>
        <Button onClick={() => setDuplicate(!duplicate)}>{g.duplicate}</Button>
        <Button onClick={() => setDrawer(true)}>{g.drawer}</Button>
        <Button onClick={() => setModal(true)}>{g.modal}</Button>
        <Button ref={trigger} id="feedback-menu-trigger" onClick={() => setMenu(!menu)}>{g.menu}</Button>
        {menu && <Menu triggerRef={trigger} items={[{ id: "save", label: g.saved }]} onSelect={() => {}} onClose={() => setMenu(false)} />}
      </div>
      <div className="u-feedback-grid"><section><h2 className="u-h2">{g.boundary}</h2>
        <ErrorBoundary><Broken broken={broken} /></ErrorBoundary></section>
        <Card><h2 className="u-h2">{g.status}</h2><p>{g.detail}</p><p className="c-note">{g.privacy}</p>
          <div className="u-feedback-controls"><Button onClick={() => status("restarting")}>{feedback.coreRestarting}</Button>
            <Button onClick={() => status("failed")}>{feedback.coreFailed}</Button>
            <Button onClick={() => status("ready")}>{feedback.coreReady}</Button></div></Card>
      </div></PageFrame>{overlay && drawerContent}
      {duplicate && <FeedbackHost coreStatusListener={listener}><p className="c-note">{g.duplicate}</p></FeedbackHost>}
    </FeedbackHost>;
  const modalContent = <Modal open={modal} titleId="feedback-modal-title" onClose={() => setModal(false)}>
      <h2 id="feedback-modal-title">{g.modal}</h2><p>{g.subtitle}</p><div className="c-modal__actions">
        <Button onClick={() => setModal(false)}>{g.cancel}</Button><Button onClick={() => setModal(false)}>{g.confirm}</Button></div>
    </Modal>;
  if (window.location.pathname.endsWith("dev-shell.html")) return <><AppShell globalFeedback>{content}</AppShell>{modalContent}</>;
  return <div className="l-app" data-ready={ready}><TopBar /><NavRail route="today" />
    <div className="l-body">{content}</div><StatusBar />{modalContent}</div>;
}
createRoot(document.getElementById("root")!, feedbackRootOptions).render(<StrictMode><Gallery /></StrictMode>);
