/**
 * 兑换成功的「光带扫过」特效（参考 glimm.dev 的 shader page transition）：
 * 一道高斯衰减的光带从左到右扫过整个应用窗口（全屏），带内是弹窗自己的四色渐变（钴蓝 → 琥珀 → 朱红 → 暖白），
 * 边缘有波浪与涟漪扰动，扫完后整层淡出。纯 WebGL，无依赖。
 * 用法：await sweepGlimm(null, { sweepMs: 1100, outroMs: 380, dark: false })  // host 为空 = 全屏覆盖整个应用窗口
 */
const VERT = 'attribute vec2 p; void main(){ gl_Position = vec4(p, 0.0, 1.0); }'
const FRAG = `
precision highp float;
uniform vec2 uRes; uniform float uT, uProg, uTight, uWave, uRipple, uAlpha, uDark;
uniform vec3 uC0, uC1, uC2, uC3;
vec3 ramp(float t){ t = clamp(t, 0.0, 1.0); vec3 a = mix(uC0, uC1, smoothstep(0.0, 0.34, t)); vec3 b = mix(uC2, uC3, smoothstep(0.67, 1.0, t)); return mix(a, b, smoothstep(0.34, 0.67, t)); }
void main(){
  vec2 uv = gl_FragCoord.xy / uRes; float asp = uRes.x / uRes.y;
  float wave = sin(uv.y * 9.0 + uT * 5.0) * uWave + sin(uv.y * 23.0 - uT * 3.0) * uWave * 0.35;
  float ripple = sin((uv.x * asp + uv.y) * 40.0 - uT * 12.0) * uRipple;
  float head = uProg * 1.6 - 0.3 + wave + ripple;          // 光带前沿：从 -0.3 扫到 1.3
  float d = uv.x - head;                                     // 前沿之后为负（已扫过）
  float band = exp(-d * d * uTight);                         // 高斯光带
  float behind = smoothstep(0.0, 0.02, -d);                  // 只有已扫过的一侧有余辉
  float tail = behind * exp(-(-d) * 5.0) * 0.42;             // 余辉随距离迅速衰减
  float t = clamp(0.5 - d * 1.8, 0.0, 1.0);                  // 带内颜色沿扫描方向铺渐变
  vec3 col = ramp(t + sin(uv.y * 6.0 + uT * 2.0) * 0.06);
  float glow = band + tail;
  float core = exp(-d * d * uTight * 6.0) * 0.9;             // 前沿一线白热
  vec3 rgb = col * glow + vec3(1.0, 0.98, 0.92) * core;
  float a = clamp(glow * (uDark > 0.5 ? 1.0 : 0.92) + core, 0.0, 1.0) * uAlpha;
  gl_FragColor = vec4(rgb * a, a);                           // premultiplied
}`
const hex = (h) => [parseInt(h.slice(1, 3), 16) / 255, parseInt(h.slice(3, 5), 16) / 255, parseInt(h.slice(5, 7), 16) / 255]
export const PALETTE = { c0: '#2F5BEA', c1: '#F2B233', c2: '#E8442B', c3: '#F2EDE0' }

export function sweepGlimm(host, { sweepMs = 1100, outroMs = 380, tight = 60, wave = 0.035, ripple = 0.008, dark = false, palette = PALETTE } = {}) {
  return new Promise((resolve) => {
    const cv = document.createElement('canvas')
    const full = !host || host === document.body            // 默认全屏：盖住整个应用窗口，不只盖弹窗
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const cw = full ? window.innerWidth : host.clientWidth, ch = full ? window.innerHeight : host.clientHeight
    const W = Math.max(2, Math.round(cw * dpr)), H = Math.max(2, Math.round(ch * dpr))
    cv.width = W; cv.height = H
    Object.assign(cv.style, full
      ? { position: 'fixed', inset: '0', width: '100vw', height: '100vh', pointerEvents: 'none', zIndex: 16000, mixBlendMode: dark ? 'screen' : 'normal' }
      : { position: 'absolute', inset: '0', width: '100%', height: '100%', pointerEvents: 'none', zIndex: 20, mixBlendMode: dark ? 'screen' : 'normal' })
    ;(full ? document.body : host).appendChild(cv)
    const gl = cv.getContext('webgl', { premultipliedAlpha: true, alpha: true, antialias: false })
    if (!gl) { cv.remove(); return resolve(false) }
    const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) console.error('[glimm] shader', gl.getShaderInfoLog(s)); return s }
    const prog = gl.createProgram(); gl.attachShader(prog, sh(gl.VERTEX_SHADER, VERT)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FRAG)); gl.linkProgram(prog); gl.useProgram(prog)
    const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
    const loc = gl.getAttribLocation(prog, 'p'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)
    const U = (n) => gl.getUniformLocation(prog, n)
    gl.uniform2f(U('uRes'), W, H); gl.uniform1f(U('uTight'), tight); gl.uniform1f(U('uWave'), wave); gl.uniform1f(U('uRipple'), ripple); gl.uniform1f(U('uDark'), dark ? 1 : 0)
    gl.uniform3fv(U('uC0'), hex(palette.c0)); gl.uniform3fv(U('uC1'), hex(palette.c1)); gl.uniform3fv(U('uC2'), hex(palette.c2)); gl.uniform3fv(U('uC3'), hex(palette.c3))
    gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA); gl.viewport(0, 0, W, H)
    const uT = U('uT'), uProg = U('uProg'), uAlpha = U('uAlpha')
    const t0 = performance.now(); const total = sweepMs + outroMs
    const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2)
    const frame = (now) => {
      const el = now - t0; const p = ease(Math.min(1, el / sweepMs)); const alpha = el <= sweepMs ? 1 : Math.max(0, 1 - (el - sweepMs) / outroMs)
      gl.uniform1f(uT, el / 1000); gl.uniform1f(uProg, p); gl.uniform1f(uAlpha, alpha)
      gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT); gl.drawArrays(gl.TRIANGLES, 0, 3)
      if (el < total) requestAnimationFrame(frame); else { try { gl.getExtension('WEBGL_lose_context')?.loseContext() } catch (e) {} cv.remove(); resolve(true) }
    }
    requestAnimationFrame(frame)
  })
}
