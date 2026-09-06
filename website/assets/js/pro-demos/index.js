/* ════════════════════════════════════════════════════════════
   pro-demos / index.js — 对外入口
   官网：import { createProPanel } from "./pro-demos/index.js"（gsap 传 window.gsap）
   应用：import { createProPanel } from "@website/js/pro-demos/index.js"（gsap 传 npm 包）
   样式在 website/assets/css/pro-demos.css；各场景文件自带的局部样式由这里注入一次。
   ════════════════════════════════════════════════════════════ */
import { PRO_GROUPS, PRO_ITEMS, PRO_TOTAL, PRO_BY_KEY, PRO_HERO_MODULES } from "./catalog.js";
import { createProStage, createProList, createProPanel as _createProPanel } from "./stage.js";
import edit, { css as editCss } from "./scenes/edit.js";
import addA, { css as addACss } from "./scenes/add-a.js";
import addB, { css as addBCss } from "./scenes/add-b.js";
import action, { css as actionCss } from "./scenes/action.js";
import moments, { css as momentsCss } from "./scenes/moments.js";
import group, { css as groupCss } from "./scenes/group.js";
import contact, { css as contactCss } from "./scenes/contact.js";
import alert, { css as alertCss } from "./scenes/alert.js";

export { PRO_GROUPS, PRO_ITEMS, PRO_TOTAL, PRO_BY_KEY, PRO_HERO_MODULES, createProStage, createProList };

export const SCENES = { ...edit, ...addA, ...addB, ...action, ...moments, ...group, ...contact, ...alert };
export const SCENE_CSS = [editCss, addACss, addBCss, actionCss, momentsCss, groupCss, contactCss, alertCss].filter(Boolean).join("\n");

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
