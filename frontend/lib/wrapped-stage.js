// 年度总结「画幅舞台」的纯几何层：画幅预设、设计尺寸、贴合缩放。
// 无 Vue / DOM 依赖，可直接 node --test。
//
// 核心约定：deck 不再等于浏览器视口，而是渲染进一个**设计像素恒定**的舞台盒，
// 舞台再整体 transform: scale 贴合窗口。卡片里的一切尺寸都相对舞台，
// 于是「换画幅」= 换舞台盒的宽高比，而不是让每张卡去做响应式断点。

// 恒定设计面积（= 1600×900）。换画幅时守恒的是面积而不是高度：
// 若守恒高度 900，9:16 只有 506px 宽，Card07 的 12 列 bento 会直接压塌。
// 守恒面积则「字号 ÷ 画面」的观感在各画幅间保持一致。
export const STAGE_AREA = 1600 * 900

// 画幅预设。exportSize 为该画幅在各平台的推荐导出像素（长边 1080 基线）。
// 覆盖依据见 docs/wrapped-frames.md（2026-08 调研）。
export const FRAME_PRESETS = [
  {
    id: 'fit',
    ratio: 0,
    label: '跟随窗口',
    caption: '自由',
    exportSize: null,
    platforms: '桌面浏览 · 全屏演示'
  },
  {
    id: '9:16',
    ratio: 9 / 16,
    label: '9:16',
    caption: '竖屏满屏',
    exportSize: [1080, 1920],
    platforms: '朋友圈单图 · 抖音 · 快手 · 视频号 · Story / Reels'
  },
  {
    /* 手机原生比例（厂商口径的 20:9，宽高写法就是 9:20 = 0.45）。
       与其它档不同，这一档不是给社交平台的：各平台竖版规格都按 9:16 裁，
       1080×2400 发出去会被切掉约 12% 的上下，在 19.5:9 的机器上又要留黑边。
       它的用途是「自留」——壁纸 / 锁屏 / 自己手机上满屏看。 */
    id: '9:20',
    ratio: 9 / 20,
    label: '9:20',
    caption: '手机满屏',
    exportSize: [1080, 2400],
    platforms: '自留壁纸 · 锁屏（20:9 手机原生；发社交平台会被裁）'
  },
  {
    id: '3:4',
    ratio: 3 / 4,
    label: '3:4',
    caption: '小红书',
    exportSize: [1080, 1440],
    platforms: '小红书笔记 · 抖音图文 · Instagram 主页宫格'
  },
  {
    id: '4:5',
    ratio: 4 / 5,
    label: '4:5',
    caption: '信息流竖版',
    exportSize: [1080, 1350],
    platforms: 'Instagram · Facebook · Threads · LinkedIn'
  },
  {
    id: '1:1',
    ratio: 1,
    label: '1:1',
    caption: '九宫格',
    exportSize: [1080, 1080],
    platforms: '朋友圈九宫格 · 微博 · QQ空间 · B站动态'
  },
  {
    id: '4:3',
    ratio: 4 / 3,
    label: '4:3',
    caption: '横版',
    exportSize: [1440, 1080],
    platforms: '图文横版 · 演示稿'
  },
  {
    id: '16:9',
    ratio: 16 / 9,
    label: '16:9',
    caption: '宽屏',
    exportSize: [1920, 1080],
    platforms: 'X 时间线 · B站封面 · 网页分享卡'
  }
]

export const DEFAULT_FRAME_ID = 'fit'

export const FRAME_STORAGE_KEY = 'wrapped.frame'

export function findFrame (id) {
  return FRAME_PRESETS.find((f) => f.id === id) || null
}

// 未知/过期的画幅 id 一律回落到「跟随窗口」，不抛错。
export function normalizeFrameId (raw) {
  const id = typeof raw === 'string' ? raw.trim() : ''
  return findFrame(id) ? id : DEFAULT_FRAME_ID
}

// 画幅档位：卡片按这个分档做重排，而不是按浏览器窗口宽度。
// wide 与今天的桌面横屏等价，是零回归基线。
export function frameTier (ratio) {
  const r = Number(ratio)
  if (!Number.isFinite(r) || r <= 0) return 'wide'
  if (r >= 1.5) return 'wide'
  if (r >= 1.15) return 'landscape'
  if (r >= 0.9) return 'square'
  if (r >= 0.66) return 'portrait'
  return 'tall'
}

// 舞台设计尺寸。ratio<=0（跟随窗口）时返回 host 实测尺寸，scale 恒为 1。
export function designSize (ratio, hostW = 0, hostH = 0) {
  const r = Number(ratio)
  if (!Number.isFinite(r) || r <= 0) {
    /* 跟随窗口。
       宽屏窗口：舞台即窗口、scale 恒 1，与舞台化之前逐像素一致（桌面浏览零回归）。

       ⚠️ 竖屏窗口（手机）不能这么做：那样设计画布就变成 393×852 这种真实像素，
       而竖幅版式的绝对 px 全是按 900×1600 的设计画布定的——标题按 900 宽的尺寸
       画在 393 宽的画布上会撑爆，按可用空间自适应的构件反而被挤成一条。
       所以竖屏时按「与窗口同比例的恒定面积画布」排版再整体缩放，与选定画幅走同一套规则，
       手机才能拿到真正为竖幅设计的版面，且铺满屏幕、没有上下黑边。 */
    const hw = Math.max(1, Math.round(hostW) || 1)
    const hh = Math.max(1, Math.round(hostH) || 1)
    const hostRatio = hw / hh
    if (hostRatio >= 1.15) return { w: hw, h: hh }
    return designSize(hostRatio, hw, hh)
  }
  // 取偶数，避免 1px 中线落在半像素上
  const h = Math.max(2, Math.round(Math.sqrt(STAGE_AREA / r) / 2) * 2)
  const w = Math.max(2, Math.round((h * r) / 2) * 2)
  return { w, h }
}

// 舞台贴合：等比缩放 + 居中，缩放值吸附到设备像素整数边界（避免相邻盒子间 1px 发丝缝）。
// 不封顶 scale——封顶会让大屏永远挂着一圈信箱边。
export function fitStage (hostW, hostH, w, h, dpr = 1) {
  const ok = [hostW, hostH, w, h].every((n) => Number.isFinite(n) && n > 0)
  if (!ok) return { scale: 1, left: 0, top: 0 }

  const raw = Math.min(hostW / w, hostH / h)
  const ratio = Number.isFinite(dpr) && dpr > 0 ? dpr : 1
  const quantum = Math.max(1, Math.round(w * ratio))
  const scale = Math.max(0.05, Math.floor(raw * quantum) / quantum)

  return {
    scale,
    left: Math.round((hostW - w * scale) / 2),
    top: Math.round((hostH - h * scale) / 2)
  }
}

// 导出倍率：把设计尺寸提升到平台推荐像素所需的 scale。
// 无 exportSize（跟随窗口）时按 2 倍兜底。
export function exportScale (frame, design) {
  const target = frame && Array.isArray(frame.exportSize) ? frame.exportSize : null
  const w = design && design.w > 0 ? design.w : 0
  if (!target || !w) return 2
  // 不要钳到 ≥1：1:1 的设计盒是 1200 而目标是 1080，钳了就会出成 1200×1200。
  // 只挡住荒谬的下限。
  return Math.max(0.25, target[0] / w)
}
