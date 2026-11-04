const hosts = new Set<symbol>();
const listeners = new Set<() => void>();
interface RootSnapshot { owner: symbol; root: HTMLElement; }
let current: RootSnapshot | null = null;
let created = false;
function publish() { for (const fn of [...listeners]) fn(); }
export const feedbackRootSnapshot = () => current;
export const feedbackRootServerSnapshot = () => null;
export function subscribeFeedbackRoot(fn: () => void) {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}
export function registerFeedbackHost(token: symbol): () => void {
  hosts.add(token);
  if (!current) {
    let root = document.getElementById("feedback-root");
    created = !root;
    if (!root) { root = document.createElement("div"); root.id = "feedback-root"; document.body.append(root); }
    current = { owner: token, root };
    publish();
  }
  return () => {
    hosts.delete(token);
    if (!current || current.owner !== token) return;
    const next = hosts.values().next().value;
    if (next) current = { ...current, owner: next };
    else { if (created) current.root.remove(); current = null; created = false; }
    publish();
  };
}
