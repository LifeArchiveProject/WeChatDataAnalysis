/* 开场卡面：照搬样张甲（v2-pearl/card.js）的 drawCard("color") —— 纯 2D canvas。
   明亮的冰蓝 · 薰衣草 · 蜜桃全息渐变卡面、右侧扭索纹圆环与中心渐变圆章、渐变大字、左上品牌与「高级版」、右上 PRO 胶囊。
   不加载 three / WebGL，没有物理材质和色调映射（那会把卡面压暗，用户要的就是这张亮的）。
   - 只保留甲的颜色通道（高度 / ORM 两个通道是给 WebGL 贴图用的，这里用不上），每一笔的坐标、颜色、透明度照抄。
   - 拉丁字（大字 77、字标 WeChatDataAnalysis、PRO）照甲写 Geist：用户喜欢的那张卡上，两个 7 的顶横连成一条、竖笔带弧度，就是 Geist。
     官网自托管并预加载了 Geist 可变字重（assets/fonts/geist-latin.woff2），调用方先等它加载好再画（main.js），
     否则会画成回退的 Helvetica Neue / Arial（两个 7 之间有缝、竖笔是直的），那不是用户要的样子。
   - 卡面上的数字由调用方传进来（main.js 从页面上的 data-pro-total / data-pro-groups 读，sync-site-catalog --check 核对的就是那两处）。
   - o.sub：「9 组 · 注册送 1 天试用」这一行的字号（卡面坐标）；手机上卡只有 300 多像素宽，甲的 44 会缩到 8px 以下，调用方传大一档。

   拆层（给开场卡的跟手视差用）：静止时卡面就是底版这一整张（与原来逐像素相同）。倾斜时才露出两小块只包住全息章的方块 canvas（章外一圈底色，半径 176；
   章外沿 171.5、扭索纹内沿 206，中间只有底色）：补丁（同一个圆里只铺底色，盖住底版上的章）与章（从底版原样拷来的位图），章随倾斜比卡面多挪几个像素，
   看着浮在扭索纹上方。不在章那层上重画一遍章：分开光栅化的笔画边缘会差几个色阶；拷位图就没有这个问题。
   为什么不让底版常年挖掉章、由小方块常驻补上：浏览器把每张 canvas 的显示框按设备整像素对齐，小方块对不上底版的亚像素位置，静止时章的细线会差几十个色阶；
   只在动起来时换上，换的那一下章还没挪开，差的不到 0.3 个像素，看不出。两小块在 1920 宽时合计约 1MB（原来与底版同尺寸的章层约 10.6MB）。

   光泽遮罩（drawMask）：开场卡的光泽层（main.css .card__shine）是加色叠上去的，盖在深色字上会把字提成灰色。
   这里另画一张遮罩：整张不透明，只把深色字（字标、「高级版」、PRO、「项高级功能」与下面那行说明）挖空，大字 77 挖掉一半，
   调用方转成图片设成光泽层的 mask-image。字的位置、字体与底版同一套代码，不会对不上。光泽静止时不显示，遮罩不影响静止像素。 */
export const CW = 2048, CH = 1292; // 卡面画布（与卡片 1.585:1 一致）

const HOLO = ["#a9dcff", "#c9b8ff", "#ffd1a1", "#a9ffe0"];
const LAT = 'Geist, "Helvetica Neue", Arial, sans-serif';
const CJK = '"PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif';
const SX = 1690, SY = 620, CUT = 176; // 全息章与扭索纹的圆心；章那层拷走的圆的半径

function rr(x, X, Y, w, h, r) {
  x.beginPath();
  if (x.roundRect) { x.roundRect(X, Y, w, h, r); return; }
  x.moveTo(X + r, Y); x.arcTo(X + w, Y, X + w, Y + h, r); x.arcTo(X + w, Y + h, X, Y + h, r); x.arcTo(X, Y + h, X, Y, r); x.arcTo(X, Y, X + w, Y, r); x.closePath();
}
function pool(x, cx, cy, r, c) { const g = x.createRadialGradient(cx, cy, 0, cx, cy, r); g.addColorStop(0, c); g.addColorStop(1, "rgba(255,255,255,0)"); x.fillStyle = g; x.fillRect(0, 0, CW, CH); }

// 底
function ground(x) {
  const g = x.createLinearGradient(0, 0, CW, CH); g.addColorStop(0, "#ffffff"); g.addColorStop(.55, "#f6f4fb"); g.addColorStop(1, "#ebe7f4");
  x.fillStyle = g; x.fillRect(0, 0, CW, CH);
  pool(x, CW * .86, CH * .16, 760, "rgba(191,230,255,.42)");
  pool(x, CW * .06, CH * .98, 820, "rgba(255,224,189,.34)");
  pool(x, CW * .5, CH * .62, 640, "rgba(217,204,255,.26)");
  // 珠光薄膜：斜向几道很淡的彩虹干涉带，静止时也看得出是全息卡
  const film = x.createLinearGradient(0, CH * .1, CW, CH * .9);
  const fc = ["169,220,255", "201,184,255", "255,209,161", "169,255,224"];
  for (let i = 0; i <= 10; i++) film.addColorStop(i / 10, `rgba(${fc[i % 4]},${i % 2 ? .34 : .22})`);
  x.fillStyle = film; x.fillRect(0, 0, CW, CH);
  const sheen = x.createLinearGradient(CW * .18, 0, CW * .62, CH);
  sheen.addColorStop(0, "rgba(255,255,255,0)"); sheen.addColorStop(.45, "rgba(255,255,255,.55)"); sheen.addColorStop(.55, "rgba(255,255,255,.55)"); sheen.addColorStop(1, "rgba(255,255,255,0)");
  x.fillStyle = sheen; x.fillRect(0, 0, CW, CH);
}

// 雕版扭索纹（围着全息章）
function ring(x) {
  x.lineWidth = 1.5;
  for (let k = 0; k < 46; k++) {
    x.beginPath();
    for (let a = 0; a <= Math.PI * 2 + .01; a += Math.PI / 180) {
      const r = 236 + k * 3.1 + 22 * Math.sin(9 * a + k * .16) + 8 * Math.sin(23 * a - k * .3);
      const px = SX + r * Math.cos(a), py = SY + r * Math.sin(a);
      a === 0 ? x.moveTo(px, py) : x.lineTo(px, py);
    }
    x.strokeStyle = ["rgba(140,190,240,.30)", "rgba(170,150,240,.30)", "rgba(240,170,120,.28)"][k % 3];
    x.stroke();
  }
}

// 内框压线
function frame(x) {
  rr(x, 52, 52, CW - 104, CH - 104, 76);
  x.strokeStyle = "rgba(120,110,175,.2)"; x.lineWidth = 3; x.stroke();
}

// 字标与「高级版」
// m：画遮罩时为真（只挖字形：填一遍再描一圈外扩，把抗锯齿的边也挖掉）；画卡面时按原色填
function ink(x, m, c, s, X, Y) { if (m) x.strokeText(s, X, Y); else x.fillStyle = c; x.fillText(s, X, Y); }
function words(x, m) {
  x.textBaseline = "alphabetic";
  x.font = `600 66px ${LAT}`; x.letterSpacing = "-1px";
  ink(x, m, "#1b1a22", "WeChatDataAnalysis", 116, 200);
  x.font = `600 104px ${CJK}`; x.letterSpacing = "2px";
  ink(x, m, "#1b1a22", "高级版", 112, 340);
}

// PRO 胶囊
function pill(x, m) {
  const px0 = CW - 116 - 244, py0 = 128;
  if (!m) {
    rr(x, px0, py0, 244, 104, 52);
    const g = x.createLinearGradient(px0, py0, px0 + 244, py0 + 60); g.addColorStop(0, "#bfe6ff"); g.addColorStop(.5, "#d9ccff"); g.addColorStop(1, "#ffe0bd"); x.fillStyle = g; x.fill(); x.strokeStyle = "rgba(255,255,255,.9)"; x.lineWidth = 3; x.stroke();
  }
  x.textBaseline = "alphabetic";
  x.font = `700 56px ${LAT}`; x.letterSpacing = "8px"; x.textAlign = "center"; ink(x, m, "#1d2234", "PRO", px0 + 126, py0 + 72); x.textAlign = "start";
}

// 全息章
function seal(x) {
  const sx = SX, sy = SY, R = 168;
  if (x.createConicGradient) {
    const cg = x.createConicGradient(-.6, sx, sy);
    [...HOLO, HOLO[0]].forEach((h, i, a) => cg.addColorStop(i / (a.length - 1), h));
    x.fillStyle = cg;
  } else {
    const lg = x.createLinearGradient(sx - R, sy - R, sx + R, sy + R);
    HOLO.forEach((h, i) => lg.addColorStop(i / (HOLO.length - 1), h));
    x.fillStyle = lg;
  }
  x.beginPath(); x.arc(sx, sy, R, 0, Math.PI * 2); x.fill();
  { const rg = x.createRadialGradient(sx - 50, sy - 60, 10, sx, sy, R); rg.addColorStop(0, "rgba(255,255,255,.75)"); rg.addColorStop(.6, "rgba(255,255,255,.1)"); rg.addColorStop(1, "rgba(255,255,255,0)"); x.fillStyle = rg; x.fill(); }
  for (let i = 0; i < 15; i++) { x.beginPath(); x.arc(sx, sy, 26 + i * 9.6, 0, Math.PI * 2); x.strokeStyle = `rgba(255,255,255,${.6 - i * .025})`; x.lineWidth = 2; x.stroke(); }
  for (let i = 0; i < 48; i++) { const a = i * Math.PI / 24; x.beginPath(); x.moveTo(sx + 34 * Math.cos(a), sy + 34 * Math.sin(a)); x.lineTo(sx + (R - 10) * Math.cos(a), sy + (R - 10) * Math.sin(a)); x.strokeStyle = "rgba(255,255,255,.22)"; x.lineWidth = 1.4; x.stroke(); }
  x.beginPath(); x.arc(sx, sy, R, 0, Math.PI * 2); x.strokeStyle = "#fff"; x.lineWidth = 7; x.stroke();
  // 章心四芒星
  x.save(); x.translate(sx, sy); x.beginPath();
  { const s = 46; x.moveTo(0, -s); x.quadraticCurveTo(6, -6, s, 0); x.quadraticCurveTo(6, 6, 0, s); x.quadraticCurveTo(-6, 6, -s, 0); x.quadraticCurveTo(-6, -6, 0, -s); }
  x.fillStyle = "#ffffff"; x.fill(); x.restore();
}

// 箔压大字（77）与右侧说明
function figure(x, total, groups, sub, m) {
  x.textBaseline = "alphabetic";
  x.font = `700 610px ${LAT}`; x.letterSpacing = "-34px";
  const tx = 92, ty = CH - 118;
  if (m) { x.save(); x.globalAlpha = m; x.fillText(total, tx, ty); x.restore(); } // 遮罩：77 只挖掉一部分（m = 挖掉的比例），箔面上仍有一点光
  else {
    const g = x.createLinearGradient(tx, ty - 440, tx + 700, ty);
    g.addColorStop(0, "#7cc4fb"); g.addColorStop(.36, "#a68ff4"); g.addColorStop(.68, "#f6ae7a"); g.addColorStop(1, "#5fdcb2");
    x.fillStyle = g; x.fillText(total, tx, ty);
    x.save(); x.globalCompositeOperation = "source-atop";
    for (let i = -20; i < 60; i++) { x.beginPath(); x.moveTo(tx + i * 18, ty - 480); x.lineTo(tx + i * 18 + 280, ty + 20); x.strokeStyle = "rgba(255,255,255,.16)"; x.lineWidth = 3; x.stroke(); }
    x.restore();
  }
  const w77 = x.measureText(total).width;
  x.letterSpacing = "0px";
  x.font = `600 70px ${CJK}`;
  ink(x, m, "#1b1a22", "项高级功能", tx + w77 + 40, CH - 268);
  x.font = `500 ${sub}px ${CJK}`;
  ink(x, m, "#77748a", `${groups} 组 · 注册送 1 天试用`, tx + w77 + 42, CH - 190 + (sub - 44) * .5);
}

/* cv = { base, seal, patch }：底版与两小块（位置大小按位图整像素换算成卡宽 / 卡高的百分比写在它们的 style 上）；S = 卡面单位到位图像素的缩放。 */
export function drawCard(cv, S = 1, o = {}) {
  const total = String(o.total ?? 80), groups = String(o.groups ?? 11), sub = o.sub || 44;
  const w = Math.round(CW * S), h = Math.round(CH * S);
  cv.base.width = w; cv.base.height = h;
  const x = cv.base.getContext("2d");
  x.setTransform(S, 0, 0, S, 0, 0);
  ground(x); ring(x); frame(x); words(x); pill(x); seal(x); figure(x, total, groups, sub); // 原样的一整张，画完不再动它
  // 两小块：取包住章的整像素方块（四周各多留 1 像素）
  const x0 = Math.floor((SX - CUT) * S) - 1, y0 = Math.floor((SY - CUT) * S) - 1;
  const sw = Math.ceil((SX + CUT) * S) + 1 - x0, sh = Math.ceil((SY + CUT) * S) + 1 - y0;
  const pc = (v, of) => `${(v / of * 100).toFixed(5)}%`, box = { left: pc(x0, w), top: pc(y0, h), width: pc(sw, w), height: pc(sh, h) };
  const clip = (c) => { c.setTransform(S, 0, 0, S, -x0, -y0); c.beginPath(); c.arc(SX, SY, CUT, 0, Math.PI * 2); c.clip(); }; // 圆心相对像素网格的小数部分与底版上一样
  for (const c of [cv.seal, cv.patch]) { c.width = sw; c.height = sh; Object.assign(c.style, box); }
  const y = cv.seal.getContext("2d");
  clip(y); y.setTransform(1, 0, 0, 1, 0, 0); y.drawImage(cv.base, x0, y0, sw, sh, 0, 0, sw, sh); // 位图对位图 1:1 拷过去
  const p = cv.patch.getContext("2d");
  clip(p); ground(p); // 补丁：同一个圆里只有底色
  return cv;
}

/* 光泽遮罩：alpha 1 = 光泽照常，0 = 挖空。c 是一张离屏 canvas，S 可以比底版低（遮罩放大后边缘自然柔一点）。 */
export function drawMask(c, S = .5, o = {}) {
  const total = String(o.total ?? 80), groups = String(o.groups ?? 11), sub = o.sub || 44;
  c.width = Math.round(CW * S); c.height = Math.round(CH * S);
  const x = c.getContext("2d");
  x.fillStyle = "#000"; x.fillRect(0, 0, c.width, c.height);
  x.setTransform(S, 0, 0, S, 0, 0);
  x.globalCompositeOperation = "destination-out";
  x.fillStyle = x.strokeStyle = "#000"; x.lineWidth = 6; x.lineJoin = "round";
  words(x, 1); pill(x, 1); figure(x, total, groups, sub, .5);
  return c;
}
