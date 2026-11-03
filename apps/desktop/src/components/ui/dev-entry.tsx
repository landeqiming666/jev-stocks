import { createRoot } from "react-dom/client";
import { StrictMode, useEffect, useRef, useState } from "react";
import { PageFrame } from "../../shell/PageFrame";
import { NavRail } from "../../shell/NavRail";
import { TopBar } from "../../shell/TopBar";
import { StatusBar } from "../../shell/StatusBar";
import { common } from "../../i18n/zh-CN/common";
import { Icon, Button, Field, Input, Textarea, SearchInput, Radio, SegmentedControl,
  VerdictChip, Probability, MarketBadge, EngineBadge, StatusTag, Card, Table, Banner, Toast,
  Skeleton, EmptyState, Progress, Menu, Drawer, Modal, Heatmap, BarList } from "./index";
import "../../styles/tokens.css";
import "../../styles/base.css";
import "../../styles/layout.css";
import "../../styles/platform-macos.css";
import "./dev-gallery.css";

const symbols = ["ZZAR", "ZZCL", "ZZFD"];
const matrix = [[1, -0.42, 0.68], [-0.42, 1, null], [0.68, null, 1]];
const bars = [{ label: "PC 1", value: 0.46 }, { label: "PC 2", value: 0.32 }, { label: "PC 3", value: 0.22 }];

function Gallery() {
  const [overlay, setOverlay] = useState(window.innerWidth < 1200);
  const [drawer, setDrawer] = useState(true), [modal, setModal] = useState(false), [menu, setMenu] = useState(false);
  const [text, setText] = useState("   😀 Research note   "), [market, setMarket] = useState("us");
  const [view, setView] = useState("visual"), [toast, setToast] = useState(true), [selection, setSelection] = useState("");
  const triggerRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 1199px)");
    const change = () => setOverlay(media.matches);
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  const drawerContent = <Drawer open={drawer} overlay={overlay} titleId="gallery-drawer-title" onClose={() => setDrawer(false)}>
    <div className="c-drawer__head"><div className="u-grow">
      <h2 className="c-drawer__title" id="gallery-drawer-title">Drawer</h2><VerdictChip kind="overturn" />
    </div><Button variant="icon" icon="x" aria-label={common.closeDrawer} onClick={() => setDrawer(false)} /></div>
    <div className="c-drawer__body">
      <p className="c-note">Component catalogue · synthetic fixtures</p>
      <Card><MarketBadge market="us" /><p className="u-ui-heading">ZZAR · Zenith Arc Robotics</p>
        <p className="c-passage">A development fixture for focus, layout and typography.</p></Card>
      <Banner tone="info" text={common.preview} />
      <Button variant="danger" onClick={() => setModal(true)}>Modal</Button>
      <EmptyState title={common.empty} text={common.chartNoData} action={<Button>{common.refresh}</Button>} />
      <Skeleton rows={1} />
    </div>
    <div className="c-drawer__foot"><Button onClick={() => setDrawer(false)}>{common.close}</Button></div>
  </Drawer>;
  return <div className="l-app" data-ready="true">
    <TopBar /><NavRail route="risk" /><div className="l-body">
      <PageFrame asideOpen={drawer && !overlay} aside={overlay ? undefined : drawerContent} asideLabel="Evidence components">
        <header className="u-ui-header"><div><p className="c-note">U-01 · DEVELOPMENT</p><h1>Components</h1></div>
          <div className="u-row"><Button icon="chevron-right" onClick={() => setDrawer(true)}>Drawer</Button>
            <Button variant="danger" onClick={() => setModal(true)}>Modal</Button>
            <span className="u-ui-menu"><Button ref={triggerRef} id="gallery-menu-trigger" variant="icon"
              icon="more-horizontal" aria-label="Menu" aria-haspopup="menu" aria-expanded={menu}
              onClick={() => setMenu(!menu)} />
              {menu && <Menu triggerRef={triggerRef} onClose={() => setMenu(false)} onSelect={setSelection}
                items={[{ id: "save", label: common.save, icon: "check" },
                  { id: "disabled", label: common.loading, disabled: true }, { id: "close", label: common.close, danger: true }]} />}
            </span>
          </div>
        </header>
        <p className="c-note u-ui-subtitle">{common.preview} · {selection || "25 public primitives"}</p>
        <div className="u-ui-grid">
          <section className="u-ui-section"><h2 className="u-ui-heading">01 / Controls</h2>
            <div className="u-row"><Button variant="primary">{common.save}</Button><Button>{common.cancel}</Button>
              <Button variant="text">{common.refresh}</Button></div>
            <Field id="gallery-note" label="Field / Textarea" help="trim → Unicode code points" count={{ value: 0, max: 50 }}>
              <Textarea value={text} onChange={event => setText(event.target.value)} /></Field>
            <Field id="gallery-input" label="Input" error={common.chartInvalid}><Input defaultValue="ZZAR" /></Field>
            <SearchInput id="gallery-search" aria-label="Search" placeholder="ZZAR" />
            <SegmentedControl name="market" label="Market" value={market} onChange={setMarket}
              items={[{ value: "us", label: common.market.us }, { value: "cn", label: common.market.cn, disabled: true }, { value: "hk", label: common.market.hk }]} />
            <Radio name="engine" value="direct" checked label={common.engine.jev_direct} hint={common.engineTitle} onChange={() => {}} />
            <h2 className="u-ui-heading u-ui-data-title">BarList / SVD</h2>
            {view === "visual" ? <BarList items={bars} label={common.chartUnits.explainedVariance} /> :
              <Table label={common.chartUnits.explainedVariance}><tbody>{bars.map(item => <tr key={item.label}><th scope="row">{item.label}</th><td className="c-table__num">{(item.value * 100).toFixed(1)}%</td></tr>)}</tbody></Table>}
          </section>
          <section className="u-ui-section"><h2 className="u-ui-heading">02 / Feedback</h2>
            <div className="u-ui-wrap">{(["overturn", "weaken", "support", "none", "uncertain"] as const).map(kind => <VerdictChip key={kind} kind={kind} />)}</div>
            <div className="u-row"><Probability value={0.9} /><MarketBadge market="us" /><StatusTag tone="ok">OK</StatusTag><Icon name="info" size={20} label="Information" /></div>
            <EngineBadge active="jev_direct" modelId="jev-1.14.0" state="degraded" />
            <Banner tone="warn" text={common.sourceDegraded} action={<Button>{common.retry}</Button>} />
            <Progress value={46} max={100} label={common.scanning} />
            <div className="u-row"><Button loading>{common.refresh}</Button><Button disabled disabledReason={common.notReady}>{common.save}</Button></div>
            {toast && <Toast tone="error" text={common.chartInvalid} onClose={() => setToast(false)} />}
            <section className="u-ui-section u-ui-charts"><div className="u-ui-header"><h2 className="u-ui-heading">03 / Data</h2>
            <SegmentedControl name="view" label="Chart view" value={view} onChange={setView}
              items={[{ value: "visual", label: common.chartVisualView }, { value: "table", label: common.chartTableView }]} /></div>
            <div className="u-ui-section">{view === "visual" ? <>
              <div className="u-ui-matrix"><Heatmap symbols={symbols} matrix={matrix} label={common.chartUnits.correlation} />
                <div className="c-legend"><span>−1</span><span className="c-legend__bar" aria-hidden="true" /><span>+1</span></div>
                <p className="c-note">{common.chartLegend}</p></div>
            </> : <><Table label={common.chartUnits.correlation}><thead><tr><th />{symbols.map(symbol => <th key={symbol}>{symbol}</th>)}</tr></thead>
              <tbody>{matrix.map((row, i) => <tr key={i}><th scope="row">{symbols[i]}</th>{row.map((value, j) => <td key={j} className="c-table__num">{value === null ? common.chartNoData : value.toFixed(2)}</td>)}</tr>)}</tbody></Table>
              </>}
            </div>
            </section>
          </section>
        </div>
      </PageFrame>{overlay && drawerContent}
    </div><StatusBar />
    <Modal open={modal} titleId="gallery-modal-title" onClose={() => setModal(false)}>
      <h2 id="gallery-modal-title">Modal</h2><p>{common.preview}</p>
      <div className="c-modal__actions"><Button onClick={() => setModal(false)}>{common.cancel}</Button>
        <Button variant="danger" onClick={() => setModal(false)}>{common.confirm}</Button></div>
    </Modal>
  </div>;
}

createRoot(document.getElementById("root")!).render(<StrictMode><Gallery /></StrictMode>);
