// Utilities for Wrapped heatmap rendering.

export const clamp01 = (v) => {
  const n = Number(v)
  if (!Number.isFinite(n)) return 0
  if (n < 0) return 0
  if (n > 1) return 1
  return n
}

export const maxInMatrix = (matrix) => {
  if (!Array.isArray(matrix)) return 0
  let m = 0
  for (const row of matrix) {
    if (!Array.isArray(row)) continue
    for (const v of row) {
      const n = Number(v)
      if (Number.isFinite(n) && n > m) m = n
    }
  }
  return m
}

// Color inspired by WeChat green, with a slight "gold" shift on high intensity
// (EchoTrace-style accent) while keeping the overall WeChat vibe.
export const heatColor = (value, max) => {
  const v = Number(value) || 0
  const m = Number(max) || 0
  if (!(v > 0) || !(m > 0)) return 'rgba(0,0,0,0.05)'

  // Use sqrt scaling to make low values still visible.
  const t = clamp01(Math.sqrt(v / m))

  // Hue from green (~145) -> yellow-green (~95)
  const hue = 145 - 50 * t
  const sat = 70
  const light = 92 - 42 * t
  return `hsl(${hue.toFixed(1)} ${sat}% ${light.toFixed(1)}%)`
}

// Theme-aware heat color function
export const themedHeatColor = (value, max, theme) => {
  const v = Number(value) || 0
  const m = Number(max) || 0
  const t = (v > 0 && m > 0) ? clamp01(Math.sqrt(v / m)) : 0

  switch (theme) {
    case 'gameboy': {
      // Game Boy 4-color palette: #0f380f, #306230, #8bac0f, #9bbc0f
      if (t === 0) return '#9bbc0f'
      if (t < 0.33) return '#8bac0f'
      if (t < 0.66) return '#306230'
      return '#0f380f'
    }
    case 'dos': {
      // DOS green phosphor: from dark to bright green
      if (t === 0) return 'rgba(51, 255, 51, 0.1)'
      const light = 20 + 60 * t
      return `hsl(120 100% ${light.toFixed(1)}%)`
    }
    case 'vhs': {
      // VHS: from dark blue to pink/magenta
      if (t === 0) return 'rgba(15, 52, 96, 0.3)'
      // Interpolate from #0f3460 (dark blue) to #e94560 (pink)
      const r = Math.round(15 + (233 - 15) * t)
      const g = Math.round(52 + (69 - 52) * t)
      const b = Math.round(96 + (96 - 96) * t)
      return `rgb(${r}, ${g}, ${b})`
    }
    default:
      // Modern (off) - use original heatColor
      return heatColor(value, max)
  }
}

export const formatHourRange = (hour) => {
  const h = Number(hour)
  if (!Number.isFinite(h)) return ''
  const hh = String(h).padStart(2, '0')
  return `${hh}:00-${hh}:59`
}

