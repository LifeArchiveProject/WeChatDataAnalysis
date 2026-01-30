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

export const formatHourRange = (hour) => {
  const h = Number(hour)
  if (!Number.isFinite(h)) return ''
  const hh = String(h).padStart(2, '0')
  return `${hh}:00-${hh}:59`
}

