/* ════════════════════════════════════════════════════════════
   pro-demos / index.js — 对外入口
   官网：import { createProPanel } from "./pro-demos/index.js"（gsap 传 window.gsap）
   应用：import { createProPanel } from "@website/js/pro-demos/index.js"（gsap 传 npm 包）
   样式在 website/assets/css/pro-demos.css；各场景文件自带的局部样式由这里注入一次。
   ════════════════════════════════════════════════════════════ */
import { PRO_GROUPS, PRO_ITEMS, PRO_TOTAL, PRO_BY_KEY, PRO_LOCAL_ITEMS } from "./catalog.js";
import { createProStage, createProList, createProPanel as _createProPanel } from "./stage.js";
import edit, { css as editCss } from "./scenes/edit.js";
import addA, { css as addACss } from "./scenes/add-a.js";
import addB, { css as addBCss } from "./scenes/add-b.js";
import action, { css as actionCss } from "./scenes/action.js";
import moments, { css as momentsCss } from "./scenes/moments.js";
import group, { css as groupCss } from "./scenes/group.js";
import contact, { css as contactCss } from "./scenes/contact.js";
import automation, { css as automationCss } from "./scenes/automation.js";

export { PRO_GROUPS, PRO_ITEMS, PRO_TOTAL, PRO_BY_KEY, PRO_LOCAL_ITEMS, createProStage, createProList };

function overviewScene({ root, kit, tl, reduced, item }) {
  const card = kit.h("section", "pd-overview");
  card.append(
    kit.h("span", "pd-overview__label", "高级版功能介绍"),
    kit.h("h2", "pd-overview__title", item.name || "高级版功能"),
    kit.h("p", "pd-overview__caption", item.caption || ""),
  );
  kit.mount(card, root);

  const labels = Array.isArray(item.flow) ? item.flow.filter(Boolean).slice(0, 3) : [];
  const steps = (labels.length ? labels : [item.caption || item.name || "功能说明"])
    .map((label) => ({ label, icon: "dots" }));
  const flow = kit.workflow(steps, { title: "说明步骤" });
  tl.fromTo(card, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: reduced ? 0.01 : 0.4, ease: "power3.out" })
    .add(flow.in(), 0.08);
  return tl;
}

const sceneMap = { ...edit, ...addA, ...addB, ...action, ...moments, ...group, ...contact, ...automation };
for (const item of PRO_ITEMS) {
  if (item.overview && typeof sceneMap[item.key] !== "function") sceneMap[item.key] = overviewScene;
}
export const SCENES = sceneMap;

const overviewCss = `
.pd-overview {
  position: absolute; inset: 30px 28px 42px; display: flex; flex-direction: column; justify-content: center; gap: 14px;
  padding: 26px 30px; border: 1px solid var(--pd-line-strong); border-radius: 14px;
  background: linear-gradient(135deg, rgba(22, 29, 25, 0.96), rgba(10, 16, 12, 0.9));
  box-shadow: inset 0 0 32px rgba(61, 242, 141, 0.035);
}
.pd-overview__label {
  align-self: flex-start; padding: 4px 8px; border: 1px solid rgba(61, 242, 141, 0.32); border-radius: 3px;
  color: var(--pd-neon); font: 10px var(--pd-mono); letter-spacing: 0.12em;
}
.pd-overview__title { color: var(--pd-ink); font-size: 28px; line-height: 1.25; font-weight: 700; }
.pd-overview__caption { max-width: 510px; color: var(--pd-dim); font-size: 15px; line-height: 1.7; }
`;
export const SCENE_CSS = [editCss, addACss, addBCss, actionCss, momentsCss, groupCss, contactCss, automationCss, overviewCss].filter(Boolean).join("\n");

let cssInjected = false;
export function injectSceneCss() {
  if (cssInjected || typeof document === "undefined" || !SCENE_CSS) return;
  cssInjected = true;
  const s = document.createElement("style");
  s.dataset.pdScenes = "";
  s.textContent = SCENE_CSS;
  document.head.appendChild(s);
}

export function createProPanel(host, opts = {}) {
  injectSceneCss();
  return _createProPanel(host, { groups: PRO_GROUPS, items: PRO_ITEMS, scenes: SCENES, ...opts });
}

// 哪些能力还没有场景：lab 页与测试用
export const missingScenes = () => PRO_ITEMS.filter((it) => typeof SCENES[it.key] !== "function").map((it) => it.key);
