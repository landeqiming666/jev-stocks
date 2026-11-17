import { Table } from "../../components/ui";
import type { Settings } from "../../rpc";
import { settings as text } from "../../i18n/zh-CN/settings";
import { Section } from "./Section";
export function PrivacySection({ settings }: { settings: Settings }) {
  return <Section title={text.sections[3]}><p>{text.privacy}</p><p className="p-settings__help">{text.privacyHelp}</p>
    <Table label={text.domains}><thead><tr>{[text.domain, text.purpose, text.sends].map(label => <th key={label} scope="col">{label}</th>)}</tr></thead>
      <tbody>{settings.allowedDomains.map(rule => <tr key={rule.domain}><td className="u-mono">{rule.domain}</td><td>{rule.purpose}</td><td>{rule.sends}</td></tr>)}</tbody>
    </Table></Section>;
}
