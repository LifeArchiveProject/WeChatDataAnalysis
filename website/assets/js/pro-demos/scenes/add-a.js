/* ════════════════════════════════════════════════════════════
   scenes / add-a.js — 消息补录 A（文字 / 图片 / 文件 / 语音 / 视频 / 表情 / 转账记录 / 红包记录 / 位置）
   每个场景：({ gsap, kit, tl, root, reduced, item }) => 把动画编进 tl（可返回 tl）。
   约定：所有补间都挂在 tl 上（不要裸调 gsap.to），舞台切换时靠 kill(tl) 清场。
   时长 4–7 秒，结尾用 kit.ok() 盖「已写入」印章并停留。

   九个场景同一张脸（kit.insertFlow）：
   seed(3) → 光标停在第 2 行下方 → 琥珀插槽线 + 「⊕ 补录」→ 点药丸 → 抽屉滑入（类型芯片命中）
   → 预览区弹出内容 → beat（每种类型一个小动作）→ 保存 → 抽屉收起 → 新行落进聊天（tag 补录）→ 印章。
   build(previewMode) 会被调两次（预览一次、真插入一次），每次都返回全新节点。
   ════════════════════════════════════════════════════════════ */

const NBSP = "\u00a0";
const TEXT_LINE = "刚到，先把照片发你";
const RP_LINE = "恭喜发财，大吉大利";
const FILE_NAME = "报销明细.xlsx";
const LOC_ADDR = "建国路 88 号 B1";

/* 数字类滚表的格式器 */
const fmtMB = (v) => `${v.toFixed(1)} MB`;
const fmtKB = (v) => `${v.toFixed(1)} KB`;
const fmtSec = (v) => `${Math.round(v)}″`;
const fmtYuan = (v) => `¥${v.toFixed(2)}`;

/* 一个只在预览区用的竖排容器：卡片 + 一行 mono 小注 */
const stack = (kit, ...children) => { const w = kit.h("div", "pd-adda-stack"); w.append(...children); return w; };

/* ───────────────────────── 九个类型：各自的 build 与 beat ───────────────────────── */

const TYPES = {
  /* 文字：预览气泡从空打字成整句，表单「内容」字段同步打字；插入时是完整文案 */
  "add-text": {
    type: "文字", side: "r", en: "INSERT · TEXT", fields: [["内容", ""]],
    build(kit, pv, side) {
      const b = kit.bubble(pv ? "" : TEXT_LINE, side);
      if (pv) b.classList.add("pd-adda-empty");
      return b;
    },
    beat({ gsap, kit, content, comp }) {
      const field = comp.form.rows[2];
      const t = gsap.timeline();
      t.call(() => field.classList.add("is-edit"))
        .add(kit.type(field.value, TEXT_LINE, { cps: 12 }), 0.08)
        .add(kit.type(content, TEXT_LINE, { cps: 12, caret: false }), "<")
        .to({}, { duration: 0.2 });
      return t;
    },
  },

  /* 图片：骨架先闪一道光，图标再落定，下面一行 mono 小注把体积从 0 滚到 1.2 MB */
  "add-image": {
    type: "图片", side: "l", en: "INSERT · IMAGE",
    build(kit, pv) {
      const card = kit.card.image();
      if (!pv) return card;
      const ic = card.querySelector(".pd-ic");
      const shine = kit.h("i", "pd-adda-shine");
      card.appendChild(shine);
      kit.gsap.set(ic, { opacity: 0.12, scale: 0.7 });
      kit.gsap.set(shine, { xPercent: -110 });
      const meta = kit.h("i", "pd-adda-meta mono");
      meta.append(kit.h("span", "", "IMG_2049.jpg · "), kit.h("b", "", "0.0 MB"));
      kit.gsap.set(meta, { opacity: 0 });
      return stack(kit, card, meta);
    },
    beat({ gsap, kit, content }) {
      const ic = content.querySelector(".pd-card .pd-ic");
      const shine = content.querySelector(".pd-adda-shine");
      const meta = content.querySelector(".pd-adda-meta");
      const size = meta.querySelector("b");
      const t = gsap.timeline();
      t.to(shine, { xPercent: 110, duration: 0.5, ease: "power1.inOut" })
        .to(ic, { opacity: 1, scale: 1, duration: 0.4, ease: "back.out(2.2)" }, ">-0.15")
        .to(meta, { opacity: 1, duration: 0.2 }, "<")
        .add(kit.count(size, 1.2, { duration: 0.5, fmt: fmtMB }), "<");
      return t;
    },
  },

  /* 文件：文件名乱码落定，体积随后滚到 24.6 KB */
  "add-file": {
    type: "文件", side: "r", en: "INSERT · FILE",
    build(kit, pv) {
      const c = kit.card.file({ name: FILE_NAME, size: "24.6 KB" });
      if (pv) { const [b, i] = c.querySelectorAll(".pd-card__txt > *"); b.textContent = NBSP; i.textContent = NBSP; }
      return c;
    },
    beat({ gsap, kit, content }) {
      const [name, size] = content.querySelectorAll(".pd-card__txt > *");
      const fic = content.querySelector(".pd-card__fic");
      const t = gsap.timeline();
      t.add(kit.scramble(name, FILE_NAME, { duration: 0.6 }))
        .add(kit.count(size, 24.6, { duration: 0.45, fmt: fmtKB }), ">-0.2")
        .fromTo(fic, { scale: 0.85 }, { scale: 1, duration: 0.35, ease: "back.out(3)", immediateRender: false }, "<");
      return t;
    },
  },

  /* 语音：秒数从 0″ 滚到 6″，声波本来就在动 */
  "add-voice": {
    type: "语音", side: "l", en: "INSERT · VOICE",
    build(kit, pv, side) { return kit.card.voice({ sec: pv ? 0 : 6, side }); },
    beat({ gsap, kit, content }) {
      const sec = content.querySelector("span");
      const t = gsap.timeline();
      t.add(kit.count(sec, 6, { duration: 0.9, fmt: fmtSec }))
        .fromTo(sec, { scale: 1 }, { scale: 1.18, duration: 0.14, yoyo: true, repeat: 1, ease: "power1.inOut", immediateRender: false }, ">-0.1");
      return t;
    },
  },

  /* 视频：播放键弹出，右下角时长从 0:00 乱码落定成 0:12 */
  "add-video": {
    type: "视频", side: "r", en: "INSERT · VIDEO",
    build(kit, pv) {
      const c = kit.card.video({ dur: "0:12" });
      if (pv) {
        c.querySelector(".pd-card__dur").textContent = "0:00";
        kit.gsap.set(c.querySelector(".pd-card__play"), { scale: 0.4, opacity: 0 });
      }
      return c;
    },
    beat({ gsap, kit, content }) {
      const play = content.querySelector(".pd-card__play");
      const dur = content.querySelector(".pd-card__dur");
      const t = gsap.timeline();
      t.to(play, { scale: 1, opacity: 0.9, duration: 0.45, ease: "back.out(2.4)" })
        .add(kit.scramble(dur, "0:12", { duration: 0.6, chars: "0123456789" }), "<+0.1");
      return t;
    },
  },

  /* 表情：小小一枚歪着进来，弹起来站正，再闪一圈琥珀 */
  "add-emoji": {
    type: "表情", side: "l", en: "INSERT · EMOJI",
    build(kit, pv) {
      const card = kit.card.emoji();
      if (!pv) return card;
      kit.gsap.set(card, { scale: 0.5, rotate: -16, opacity: 0.4 });
      return stack(kit, card);
    },
    beat({ gsap, kit, content }) {
      const card = content.querySelector(".pd-card");
      const t = gsap.timeline();
      t.to(card, { scale: 1, rotate: 0, opacity: 1, duration: 0.55, ease: "back.out(2.8)" })
        .add(kit.flash(card, { color: "amber", duration: 0.6 }), ">-0.3")
        .to(card.querySelector(".pd-ic"), { rotate: 12, duration: 0.12, yoyo: true, repeat: 3, ease: "power1.inOut" }, "<");
      return t;
    },
  },

  /* 转账记录：金额从 ¥0.00 滚到 ¥520.00，落定时轻轻一顿 */
  "add-transfer": {
    type: "转账", side: "r", en: "INSERT · TRANSFER", fields: [["状态", "已收款"]],
    build(kit, pv) { return kit.card.transfer({ amount: pv ? "¥0.00" : "¥520.00", note: "转账给你" }); },
    beat({ gsap, kit, content }) {
      const amount = content.querySelector(".pd-card__main b");
      const t = gsap.timeline();
      t.add(kit.count(amount, 520, { duration: 0.9, fmt: fmtYuan }))
        .fromTo(amount, { scale: 1 }, { scale: 1.08, duration: 0.14, yoyo: true, repeat: 1, ease: "power1.inOut", immediateRender: false, transformOrigin: "0 50%" }, ">-0.1");
      return t;
    },
  },

  /* 红包记录：祝福语一个字一个字打出来 */
  "add-redpacket": {
    type: "红包", side: "l", en: "INSERT · REDPACKET",
    build(kit, pv) {
      const c = kit.card.redpacket({ text: pv ? NBSP : RP_LINE });
      if (pv) c.classList.add("pd-adda-rp");
      return c;
    },
    beat({ gsap, kit, content }) {
      const b = content.querySelector(".pd-card__main b");
      const t = gsap.timeline();
      t.add(kit.type(b, RP_LINE, { cps: 12 }), 0.05)
        .to({}, { duration: 0.15 });
      return t;
    },
  },

  /* 位置：红针从上方落到地图上，落点荡开一圈，详址同时乱码落定 */
  "add-location": {
    type: "位置", side: "r", en: "INSERT · LOCATION", seed: 2, afterRow: 1,   // 卡片高：两条往来，补在两条之间
    build(kit, pv) {
      const c = kit.card.location({ name: "老地方咖啡", addr: LOC_ADDR });
      if (!pv) return c;
      const map = c.querySelector(".pd-card__map");
      const pin = map.querySelector(".pd-ic");
      const ring = kit.h("i", "pd-adda-ring");
      map.appendChild(ring);
      kit.gsap.set(pin, { y: -16, opacity: 0 });
      kit.gsap.set(ring, { scale: 0.2, opacity: 0 });
      c.querySelector(".pd-card__txt i").textContent = NBSP;
      return c;
    },
    beat({ gsap, kit, content }) {
      const pin = content.querySelector(".pd-card__map .pd-ic");
      const ring = content.querySelector(".pd-adda-ring");
      const addr = content.querySelector(".pd-card__txt i");
      const t = gsap.timeline();
      t.to(pin, { y: 0, opacity: 1, duration: 0.5, ease: "back.out(2.4)" })
        .fromTo(ring, { scale: 0.2, opacity: 0.9 }, { scale: 1, opacity: 0, duration: 0.55, ease: "power2.out", immediateRender: false }, ">-0.15")
        .add(kit.scramble(addr, LOC_ADDR, { duration: 0.5 }), "<-0.2");
      return t;
    },
  },
};

/* ───────────────────────── 工厂：同一张脸 ───────────────────────── */

function make(key) {
  const spec = TYPES[key];
  return ({ gsap, kit, tl }) => {
    const chat = kit.chat({ title: "老地方" });
    const rows = chat.seed(spec.seed || 3);
    const flow = kit.insertFlow(chat, {
      after: rows[spec.afterRow ?? 2],      // 默认「刚落地，还是老地方见」之后
      side: spec.side,
      type: spec.type,
      fields: spec.fields || [],
      build: (pv) => spec.build(kit, pv, spec.side),
      beat: (ctx) => spec.beat({ gsap, kit, ...ctx }),
      stamp: "已写入",
      en: spec.en,
    });
    // 落在左边的行是对方发的：抽屉里的「发送方」跟着改
    if (spec.side === "l") flow.comp.form.rows[0].value.textContent = "友";
    tl.add(flow, 0);
    return tl;
  };
}

export default Object.fromEntries(Object.keys(TYPES).map((k) => [k, make(k)]));

// 本组专属的局部样式；统一注入一次
export const css = `
.pd-adda-stack { display: flex; flex-direction: column; align-items: center; gap: 7px; max-width: 100%; }
.pd-adda-meta { font-family: var(--pd-mono); font-size: 9.5px; letter-spacing: 0.12em; color: var(--pd-dim); white-space: nowrap; }
.pd-adda-meta b { color: var(--pd-amber); font-weight: 500; }
.pd-adda-shine { position: absolute; inset: 0; pointer-events: none; background: linear-gradient(100deg, transparent 28%, rgba(233, 241, 235, 0.18) 50%, transparent 72%); }
.pd-adda-empty { min-width: 46px; min-height: 32px; }
.pd-adda-ring { position: absolute; left: 50%; top: calc(50% + 8px); width: 34px; height: 34px; margin: -17px 0 0 -17px; border-radius: 50%; border: 1.5px solid var(--pd-red); pointer-events: none; }
.pd-adda-rp .pd-card__main b.is-typing::after { content: ""; display: inline-block; width: 1px; height: 12px; margin-left: 2px; vertical-align: -1px; background: #fff; animation: pdBlink 0.9s steps(2) infinite; }
`;
