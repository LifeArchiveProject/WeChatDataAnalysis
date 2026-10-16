/* ════════════════════════════════════════════════════════════
   particles.js — 全站 WebGL 舞台
   一团会变形的粒子：星云 → 钥匙 → 气泡 → 2025 → 锁
   + FBM 极光背景。全部着色器驱动，CPU 只管 morph 编排。
   ════════════════════════════════════════════════════════════ */
import * as THREE from "three";

const isMobile = matchMedia("(max-width: 768px)").matches;
const COUNT = isMobile ? 9000 : 24000;
const WORLD = 17; // 形状铺开的世界尺寸

/* ---------- 形状采样 ---------- */

function samplePixels(draw, n) {
  const S = 400;
  const cv = document.createElement("canvas");
  cv.width = cv.height = S;
  const ctx = cv.getContext("2d", { willReadFrequently: true });
  ctx.fillStyle = "#fff";
  ctx.strokeStyle = "#fff";
  draw(ctx, S);
  const data = ctx.getImageData(0, 0, S, S).data;
  const pts = [];
  for (let y = 0; y < S; y += 1) {
    for (let x = 0; x < S; x += 1) {
      if (data[(y * S + x) * 4 + 3] > 120) pts.push([x / S - 0.5, 0.5 - y / S]);
    }
  }
  const out = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    // 88% 落在形状上，12% 化作周围游尘
    if (pts.length && Math.random() > 0.12) {
      const p = pts[(Math.random() * pts.length) | 0];
      out[i * 3] = p[0] * WORLD + (Math.random() - 0.5) * 0.14;
      out[i * 3 + 1] = p[1] * WORLD + (Math.random() - 0.5) * 0.14;
      out[i * 3 + 2] = (Math.random() - 0.5) * 1.4;
    } else {
      const r = 9 + Math.random() * 9;
      const a = Math.random() * Math.PI * 2;
      out[i * 3] = Math.cos(a) * r;
      out[i * 3 + 1] = (Math.random() - 0.5) * 12;
      out[i * 3 + 2] = -2 - Math.random() * 6;
    }
  }
  return out;
}

function shapeHalo(n) {
  const out = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const arm = (i % 3) * ((Math.PI * 2) / 3);
    const t = Math.pow(Math.random(), 0.55);
    const r = 2.2 + t * 9.5;
    const a = arm + t * 2.6 + (Math.random() - 0.5) * 0.9;
    const y = (Math.random() - 0.5) * (1.6 - t * 1.1);
    if (Math.random() < 0.85) {
      out[i * 3] = Math.cos(a) * r * 1.28;
      out[i * 3 + 1] = Math.sin(a) * r * 0.62 + y;
      out[i * 3 + 2] = (Math.random() - 0.5) * 3.2;
    } else {
      const rr = 11 + Math.random() * 7;
      const aa = Math.random() * Math.PI * 2;
      out[i * 3] = Math.cos(aa) * rr;
      out[i * 3 + 1] = (Math.random() - 0.5) * 13;
      out[i * 3 + 2] = -3 - Math.random() * 5;
    }
  }
  return out;
}

function shapeKey(n) {
  return samplePixels((c, S) => {
    const u = S / 400;
    c.lineWidth = 26 * u;
    c.lineCap = "round";
    c.beginPath(); // 齿孔圆环
    c.arc(150 * u, 150 * u, 74 * u, 0, Math.PI * 2);
    c.stroke();
    c.beginPath(); // 钥匙柄
    c.moveTo(205 * u, 205 * u);
    c.lineTo(330 * u, 330 * u);
    c.moveTo(282 * u, 282 * u);
    c.lineTo(330 * u, 234 * u);
    c.moveTo(240 * u, 240 * u);
    c.lineTo(282 * u, 198 * u);
    c.stroke();
  }, n);
}

function shapeBubble(n) {
  return samplePixels((c, S) => {
    const u = S / 400;
    const r = 46 * u;
    c.beginPath();
    c.roundRect(56 * u, 96 * u, 288 * u, 170 * u, r);
    c.fill();
    c.beginPath(); // 尾巴
    c.moveTo(116 * u, 258 * u);
    c.lineTo(96 * u, 316 * u);
    c.lineTo(172 * u, 264 * u);
    c.closePath();
    c.fill();
    c.globalCompositeOperation = "destination-out"; // 打字点
    for (let i = 0; i < 3; i++) {
      c.beginPath();
      c.arc((146 + i * 54) * u, 181 * u, 17 * u, 0, Math.PI * 2);
      c.fill();
    }
  }, n);
}

function shapeYear(n, text) {
  return samplePixels((c, S) => {
    c.font = `900 ${S * 0.34}px "Unbounded","Arial Black",sans-serif`;
    c.textAlign = "center";
    c.textBaseline = "middle";
    c.fillText(text, S / 2, S / 2);
  }, n);
}

function shapeLock(n) {
  return samplePixels((c, S) => {
    const u = S / 400;
    c.lineWidth = 26 * u;
    c.beginPath(); // 锁梁
    c.arc(200 * u, 158 * u, 66 * u, Math.PI, 0);
    c.moveTo(134 * u, 158 * u);
    c.lineTo(134 * u, 196 * u);
    c.moveTo(266 * u, 158 * u);
    c.lineTo(266 * u, 196 * u);
    c.stroke();
    c.beginPath(); // 锁体
    c.roundRect(96 * u, 196 * u, 208 * u, 148 * u, 26 * u);
    c.fill();
    c.globalCompositeOperation = "destination-out"; // 锁孔
    c.beginPath();
    c.arc(200 * u, 254 * u, 20 * u, 0, Math.PI * 2);
    c.fill();
    c.fillRect(189 * u, 258 * u, 22 * u, 46 * u);
  }, n);
}

/* ---------- 着色器 ---------- */

const VERT = /* glsl */ `
uniform float uTime, uMorph, uAmp, uFly, uSize, uPR, uMouseF;
uniform vec3  uMouse;
attribute vec3  aTarget;
attribute float aRand, aScale;
varying float vRand, vFlight, vDepth;

void main() {
  float d  = clamp((uMorph - aRand * 0.42) / 0.58, 0.0, 1.0);
  float tt = d * d * (3.0 - 2.0 * d);
  vec3 pos = mix(position, aTarget, tt);

  // morph 中途的爆散飞行
  float flight = sin(tt * 3.14159265);
  pos += normalize(pos + vec3(0.001)) * flight * (1.2 + aRand * 3.0) * uFly;
  vFlight = flight;

  // 伪 curl 呼吸
  float t = uTime * 0.55;
  pos.x += sin(pos.y * 0.62 + t + aRand * 6.283) * uAmp * (0.35 + aRand * 0.65);
  pos.y += cos(pos.x * 0.53 - t * 1.18 + aRand * 4.0) * uAmp * (0.35 + aRand * 0.65);
  pos.z += sin(pos.x * 0.36 + pos.y * 0.3 + t * 0.8) * uAmp * 0.55;

  // 鼠标斥力
  vec2 diff = pos.xy - uMouse.xy;
  float dist = length(diff);
  float force = smoothstep(4.2, 0.0, dist) * uMouseF;
  pos.xy += normalize(diff + vec2(0.0001)) * force * (0.6 + aRand);

  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  gl_Position = projectionMatrix * mv;
  float tw = 0.72 + 0.4 * sin(uTime * (1.2 + aRand * 2.2) + aRand * 40.0);
  gl_PointSize = uSize * aScale * tw * uPR * (30.0 / -mv.z);
  vRand = aRand;
  vDepth = smoothstep(-52.0, -16.0, mv.z);
}`;

const FRAG = /* glsl */ `
uniform vec3 uColA, uColB, uColC;
uniform float uOpacity;
varying float vRand, vFlight, vDepth;

void main() {
  vec2 uv = gl_PointCoord - 0.5;
  float d = length(uv);
  if (d > 0.5) discard;
  float soft = smoothstep(0.5, 0.06, d);
  float core = pow(smoothstep(0.24, 0.0, d), 2.8);
  vec3 col = mix(uColA, uColB, smoothstep(0.15, 0.85, vRand));
  col = mix(col, uColC, core * 0.5);
  col += uColB * vFlight * 0.45; // 飞行时提亮
  float a = soft * (0.13 + 0.45 * vDepth) * uOpacity;
  gl_FragColor = vec4(col, a);
}`;

const AURORA_FRAG = /* glsl */ `
precision highp float;
uniform float uTime, uShift;
uniform vec2  uRes;
uniform vec3  uTint;
varying vec2 vUv;

float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1,0)), u.x),
             mix(hash(i + vec2(0,1)), hash(i + vec2(1,1)), u.x), u.y);
}
float fbm(vec2 p){
  float v = 0.0, a = 0.5;
  for (int i = 0; i < 4; i++) { v += a * noise(p); p *= 2.13; a *= 0.5; }
  return v;
}
void main(){
  vec2 uv = vUv;
  vec2 p = uv * vec2(uRes.x / uRes.y, 1.0) * 1.6;
  float t = uTime * 0.03;
  float f = fbm(p + vec2(t, uShift * 2.2) + fbm(p * 1.7 - t) * 0.9);
  vec3 base = vec3(0.012, 0.022, 0.016);
  vec3 col = base + uTint * pow(f, 2.6) * 0.55;
  col += vec3(0.02, 0.09, 0.05) * pow(fbm(p * 0.5 + t * 0.6), 3.0) * 0.8;
  float vig = smoothstep(1.35, 0.25, length(uv - 0.5) * 1.9);
  col *= mix(0.35, 1.0, vig);
  gl_FragColor = vec4(col, 1.0);
}`;

/* ---------- 主体 ---------- */

export function createStage(canvas) {
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: false,
    alpha: false,
    powerPreference: "high-performance",
  });
  const DPR = Math.min(devicePixelRatio || 1, 1.8);
  renderer.setPixelRatio(DPR);
  renderer.setClearColor(0x050807, 1);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 120);
  camera.position.set(0, 0, 30);

  // 极光背景（跟随相机的大平面，最先渲染）
  const auroraUniforms = {
    uTime: { value: 0 },
    uShift: { value: 0 },
    uRes: { value: new THREE.Vector2(1, 1) },
    uTint: { value: new THREE.Color(0x0b3d24) },
  };
  const aurora = new THREE.Mesh(
    new THREE.PlaneGeometry(2, 2),
    new THREE.ShaderMaterial({
      uniforms: auroraUniforms,
      vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.9999, 1.0); }`,
      fragmentShader: AURORA_FRAG,
      depthWrite: false,
      depthTest: false,
    })
  );
  aurora.renderOrder = -1;
  aurora.frustumCulled = false;
  scene.add(aurora);

  // 形状库
  const shapes = {
    halo: shapeHalo(COUNT),
    key: shapeKey(COUNT),
    bubble: shapeBubble(COUNT),
    year: shapeYear(COUNT, "2025"),
    lock: shapeLock(COUNT),
  };

  const geo = new THREE.BufferGeometry();
  const base = new Float32Array(shapes.halo);
  const target = new Float32Array(shapes.halo);
  const rand = new Float32Array(COUNT);
  const scale = new Float32Array(COUNT);
  for (let i = 0; i < COUNT; i++) {
    rand[i] = Math.random();
    scale[i] = 0.5 + Math.pow(Math.random(), 3.4) * 1.7;
  }
  geo.setAttribute("position", new THREE.BufferAttribute(base, 3));
  geo.setAttribute("aTarget", new THREE.BufferAttribute(target, 3));
  geo.setAttribute("aRand", new THREE.BufferAttribute(rand, 1));
  geo.setAttribute("aScale", new THREE.BufferAttribute(scale, 1));

  const uniforms = {
    uTime: { value: 0 },
    uMorph: { value: 0 },
    uAmp: { value: 0.55 },
    uFly: { value: 1 },
    uSize: { value: isMobile ? 7.5 : 9.5 },
    uPR: { value: DPR },
    uMouse: { value: new THREE.Vector3(999, 999, 0) },
    uMouseF: { value: 1.6 },
    uOpacity: { value: 0 },
    uColA: { value: new THREE.Color(0x0a5c33) },
    uColB: { value: new THREE.Color(0x35e07f) },
    uColC: { value: new THREE.Color(0xd8ffe9) },
  };

  const points = new THREE.Points(
    geo,
    new THREE.ShaderMaterial({
      uniforms,
      vertexShader: VERT,
      fragmentShader: FRAG,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    })
  );
  scene.add(points);

  /* ----- morph 编排 ----- */
  let currentShape = "halo";
  let morphTween = null;

  // 把当前插值状态烘焙进 base，避免打断时跳变
  function bake() {
    const m = uniforms.uMorph.value;
    if (m <= 0) return;
    const p = geo.attributes.position.array;
    const t = geo.attributes.aTarget.array;
    for (let i = 0; i < COUNT; i++) {
      const d = Math.min(1, Math.max(0, (m - rand[i] * 0.42) / 0.58));
      const tt = d * d * (3 - 2 * d);
      p[i * 3] += (t[i * 3] - p[i * 3]) * tt;
      p[i * 3 + 1] += (t[i * 3 + 1] - p[i * 3 + 1]) * tt;
      p[i * 3 + 2] += (t[i * 3 + 2] - p[i * 3 + 2]) * tt;
    }
    geo.attributes.position.needsUpdate = true;
    uniforms.uMorph.value = 0;
  }

  function morphTo(name, { duration = 1.7, fly = 1 } = {}) {
    if (name === currentShape || !shapes[name]) return;
    if (morphTween) morphTween.kill();
    bake();
    currentShape = name;
    geo.attributes.aTarget.array.set(shapes[name]);
    geo.attributes.aTarget.needsUpdate = true;
    uniforms.uFly.value = fly;
    morphTween = gsap.to(uniforms.uMorph, {
      value: 1,
      duration,
      ease: "power2.inOut",
      overwrite: true,
      onComplete() {
        geo.attributes.position.array.set(shapes[name]);
        geo.attributes.position.needsUpdate = true;
        uniforms.uMorph.value = 0;
        morphTween = null;
      },
    });
  }

  /* ----- 交互 & 帧循环 ----- */
  const mouseNDC = new THREE.Vector2(0, 0);
  let parallax = { x: 0, y: 0 };

  function pointerMove(e) {
    mouseNDC.x = (e.clientX / innerWidth) * 2 - 1;
    mouseNDC.y = -(e.clientY / innerHeight) * 2 + 1;
  }
  addEventListener("pointermove", pointerMove, { passive: true });

  function resize() {
    const w = innerWidth, h = innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    auroraUniforms.uRes.value.set(w, h);
  }
  addEventListener("resize", resize);
  resize();

  let scrollRot = 0;
  const api = {
    uniforms,
    aurora: auroraUniforms,
    morphTo,
    pulse(strength = 1.4) {
      gsap.fromTo(uniforms.uAmp, { value: strength }, { value: api._restAmp, duration: 1.6, ease: "expo.out", overwrite: true });
    },
    setAmp(v, dur = 1) {
      api._restAmp = v;
      gsap.to(uniforms.uAmp, { value: v, duration: dur, ease: "power2.out", overwrite: "auto" });
    },
    setOpacity(v, dur = 1) {
      gsap.to(uniforms.uOpacity, { value: v, duration: dur, ease: "power2.out", overwrite: "auto" });
    },
    setTint(hex, dur = 1.4) {
      const c = new THREE.Color(hex);
      gsap.to(auroraUniforms.uTint.value, { r: c.r, g: c.g, b: c.b, duration: dur, ease: "sine.inOut", overwrite: "auto" });
    },
    setScroll(p) {
      scrollRot = p;
      auroraUniforms.uShift.value = p;
    },
    _restAmp: 0.55,
    update(t) {
      uniforms.uTime.value = t;
      auroraUniforms.uTime.value = t;
      // 鼠标 → 世界坐标（z=0 平面）
      const v = new THREE.Vector3(mouseNDC.x, mouseNDC.y, 0.5).unproject(camera);
      const dir = v.sub(camera.position).normalize();
      const dist = -camera.position.z / dir.z;
      const world = camera.position.clone().add(dir.multiplyScalar(dist));
      uniforms.uMouse.value.lerp(world, 0.12);
      // 视差 & 滚动旋转
      parallax.x += (mouseNDC.x * 1.6 - parallax.x) * 0.04;
      parallax.y += (mouseNDC.y * 1.0 - parallax.y) * 0.04;
      camera.position.x = parallax.x;
      camera.position.y = parallax.y * 0.7;
      camera.lookAt(0, 0, 0);
      points.rotation.y = scrollRot * Math.PI * 1.15 + t * 0.02;
      points.rotation.x = Math.sin(scrollRot * Math.PI) * 0.14;
      renderer.render(scene, camera);
    },
  };
  return api;
}
