import { invoke } from "@tauri-apps/api/core";
import { useEffect, useRef, useState } from "react";
import { Banner, Button } from "../../components/ui";
import type { Bootstrap } from "../../rpc";
import { settings as text } from "../../i18n/zh-CN/settings";
import { Section } from "./Section";
const LICENSE_URL = "https://github.com/landeqiming666/jev-stocks/blob/main/THIRD_PARTY.md";
export function AboutSection({ bootstrap }: { bootstrap: Bootstrap | null }) {
  const [failed, setFailed] = useState(false);
  const alive = useRef(false);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  return <Section title={text.sections[5]}><dl className="p-settings__about">
    <div><dt>{text.version}</dt><dd className="u-mono">{bootstrap?.appVersion ?? "—"}</dd></div>
    <div><dt>{text.build}</dt><dd>{text.buildUnknown}</dd></div>
    <div><dt>{text.protocol}</dt><dd className="u-mono">{bootstrap?.protocolVersion ?? "—"}</dd></div>
  </dl><Button onClick={() => { setFailed(false); void invoke("open_external", { url: LICENSE_URL }).catch(() => { if (alive.current) setFailed(true); }); }}>{text.license}</Button>
    {failed && <Banner tone="danger" text={text.unavailable} />}<p className="p-settings__help">{text.disclaimer}</p></Section>;
}
