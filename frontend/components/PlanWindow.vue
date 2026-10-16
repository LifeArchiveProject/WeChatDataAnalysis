<template>
  <Teleport to="body">
    <Transition name="pw">
      <div v-if="open" class="pw-scrim" @mousedown.self="close">
        <section
          ref="dlgEl"
          class="pw-dlg"
          :class="{ 'is-dark': dark }"
          :style="{ '--pw-scale': scale }"
          role="dialog"
          aria-modal="true"
          aria-label="套餐与额度"
          tabindex="-1"
          @keydown.esc.prevent="close"
        >
          <div class="pw-grain" aria-hidden="true" />
          <p class="pw-intro">
            WxCDN 媒体下载服务 · 支持图片 / 视频 / 文件 / 语音<br>
            {{ DEVELOPER_CONTACT_TITLE }}
            <button type="button" class="pw-contact" @click="openDeveloperContact">{{ DEVELOPER_CONTACT_LABEL }}</button>
            <button type="button" class="pw-contact" @click="openDeveloperGroup">{{ DEVELOPER_CONTACT_HINT }}</button>。
          </p>
          <nav class="pw-index" aria-label="版本">
            <button
              v-for="t in ORDER"
              :key="t"
              type="button"
              class="pw-tier"
              :class="{ view: view === t, cur: tier === t }"
              @click="switchView(t)"
            >
              <span class="w">{{ t }}</span>
              <small>{{ tierLabel(t) }}</small>
            </button>
          </nav>
          <div ref="stackEl" class="pw-stack" @pointermove="onPointerMove" @pointerleave="onPointerLeave" @pointerdown="onPointerDown" @pointerup="onPointerUp">
            <canvas ref="cvFree" :class="{ active: view === 'Free' }" aria-hidden="true" />
            <canvas ref="cvPlus" :class="{ active: view === 'Plus' }" aria-hidden="true" />
            <canvas ref="cvPro" :class="{ active: view === 'Pro' }" aria-hidden="true" />
            <canvas ref="cvUltra" :class="{ active: view === 'Ultra' }" aria-hidden="true" />
            <canvas ref="ovUltra" class="overlay" :class="{ on: view === 'Ultra' }" aria-hidden="true" />
            <canvas ref="snapEl" class="snap-cv" aria-hidden="true" />
            <div ref="lineEl" class="pw-line" aria-hidden="true" />
          </div>
          <form class="pw-redeem" @submit.prevent="submitCode">
            <label class="pw-redeem__field" :class="{ 'is-locked': locked, 'is-ready': ready, 'is-bad': bad }">
              <span class="pre">wx-</span>
              <input
                ref="inputEl"
                type="text"
                autocomplete="off"
                spellcheck="false"
                autocapitalize="characters"
                maxlength="40"
                placeholder="XXXX-XXXX-XXXX-XXXX-XXXX"
                aria-label="兑换码"
                :disabled="locked || verifying"
                @input="onInput"
                @paste="onPaste"
              >
              <span class="count">{{ codeLen }}/20</span>
            </label>
            <button type="submit" class="pw-redeem__go" :disabled="!ready || verifying || locked">{{ verifying ? '验证中 …' : '兑换' }}</button>
            <p class="pw-redeem__msg" :key="msgKey" :class="{ err: msgErr || (!msg && hintErr), ok: msgOk, dim: !msg && !hintErr }">{{ msg || hint }}</p>
          </form>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { storeToRefs } from 'pinia'
import { ORDER, TIERS, nowSec, fmtB, localHM, localDate, normalizeRedeemCode, projectPlan, normalizeTier } from '~/lib/wxcdn-card/format.js'
import { CardMaster, CARD_W, CARD_H, CH, WIN } from '~/lib/wxcdn-card/master.js'
import { AsciiRenderer, DotMatrixRenderer, PlotterRenderer, BeadRenderer, ParticleRenderer } from '~/lib/wxcdn-card/renderers.js'
import { sweepGlimm } from '~/lib/wxcdn-card/glimm.js'
import { buildAccountAvatarUrl } from '~/lib/account-avatar'
import { useChatAccountsStore } from '~/stores/chatAccounts'
import { useCdnPlanStore } from '~/stores/cdnPlan'
import { DEVELOPER_CONTACT_TITLE, DEVELOPER_CONTACT_LABEL, DEVELOPER_CONTACT_HINT, openDeveloperContact, openDeveloperGroup } from '~/lib/developer-support'

const { open, reason, closePlanWindow } = usePlanWindow()
const store = useCdnPlanStore()
const chatAccounts = useChatAccountsStore()
const { selectedAccount, accountInfos } = storeToRefs(chatAccounts)
const apiBase = useApiBase()

const dlgEl = ref(null), stackEl = ref(null), snapEl = ref(null), lineEl = ref(null), inputEl = ref(null)
const cvFree = ref(null), cvPlus = ref(null), cvPro = ref(null), cvUltra = ref(null), ovUltra = ref(null)
const view = ref('Free')
const tier = computed(() => normalizeTier(store.tier))
const dark = ref(false)
const scale = ref(0.78)
const msg = ref(''), msgErr = ref(false), msgOk = ref(false)
const hint = ref(''), hintErr = ref(false), msgKey = ref(0), bad = ref(false), verifying = ref(false), ready = ref(false), locked = ref(false), codeLen = ref(0)
const tierLabel = (t) => (tier.value === t ? `${TIERS[t].label} · 当前` : TIERS[t].label)

/* 卡的共享状态：母版与四档渲染器只读它 */
const st = {
  view: 'Free', tier: null, connected: false, viewPlan: null,
  disp: { remaining: 0 }, reveal: { p: 1, image: null, stamp: '', stampColor: 'cobalt' },
  exhausted: false, offline: false, reduced: false, dark: false, lockedUntil: 0,
  redeem: { text: '', verifying: false }, status: '', statusColor: null,
}
let plusStyle = 'dot'
let master = null, R = {}, raf = 0, last = 0, t0 = 0, busy = false, tickTimer = 0, ambientTimer = 0, msgTimer = 0
const pointer = { x: 0, y: 0, inside: false, down: false, click: false }
let gsapMod = null
const gsap = async () => gsapMod || (gsapMod = (await import('gsap')).gsap)

/* ── 快照 → 卡状态 ── */
const syncFromStore = () => {
  const snap = store.snapshot
  st.connected = store.connected
  st.tier = tier.value
  st.lockedUntil = store.lockedUntil
  st.offline = false
  st.exhausted = store.exhausted
  locked.value = st.lockedUntil > nowSec()
  if (!st.connected) {
    const e = snap?.error || snap?.lastError || store.error
    const retryLeft = Math.max(0, Math.ceil(Number(snap?.tokenRetryUntil || 0) - nowSec()))
    hintErr.value = true
    if (store.loading) { hint.value = '正在接入 · 读取本机微信配置'; hintErr.value = false }
    else if (e?.code === 'account_frozen' || snap?.frozen) hint.value = '账号已被冻结，请联系管理员'
    else if (e?.code === 'config_unreadable') hint.value = '读不到这个账号的微信配置，先在检测页完成解密'
    else if (e?.code === 'account_unresolved') hint.value = '找不到这个账号的本机微信数据目录'
    else if (e?.code === 'invalid_config') hint.value = '服务端没能校验本机的微信配置 · 本地文件已自检通过，需服务方排查'
    else if (e?.code === 'rate_limited') hint.value = `请求太快，${retryLeft || e.retryAfterSeconds || 10} 秒后自动重试`
    else if (e?.code === 'network_error') hint.value = `没连上 wxcdn.c3o.re${retryLeft ? `，${retryLeft} 秒后自动重试` : ''}`
    else { hint.value = '未接入 · 输入兑换码即可激活'; hintErr.value = false }
    st.viewPlan = null
  } else {
    hintErr.value = false
    if (locked.value) hint.value = `兑换已锁定，${Math.ceil((st.lockedUntil - nowSec()) / 60)} 分钟后恢复 · 只锁兑换，下载照常`
    else hint.value = '输入兑换码升级或顺延'
    if (view.value === tier.value || !tier.value) st.viewPlan = { account: snap.account, quota: snap.quota }
    else st.viewPlan = projectPlan(snap.account, snap.quota, view.value)
  }
  st.view = view.value
  st.disp.remaining = Number(st.viewPlan?.quota?.remainingBytes ?? 0)
  master?.invalidate()
}
watch(() => store.snapshot, syncFromStore, { deep: true })

/* ── 图：用户自己的头像（真实实现可换成最近一次经 Worker 下载的原图） ── */
const loadImage = () => new Promise((resolve) => {
  const acc = String(selectedAccount.value || '').trim()
  if (!acc) return resolve(null)
  const info = (accountInfos.value || []).find((i) => String(i?.account || i?.name || '') === acc) || null
  const url = buildAccountAvatarUrl(apiBase, acc, info)
  if (!url) return resolve(null)
  const img = new Image(); img.crossOrigin = 'anonymous'
  img.onload = () => resolve(img); img.onerror = () => resolve(null); img.src = url
})
const develop = async (rec) => {
  if (!master) return
  const g = await gsap()
  g.killTweensOf(st.reveal); st.reveal.p = 0; st.reveal.stamp = ''; master.invalidate()
  const up = () => master?.invalidate()
  const done = () => { if (rec) { st.reveal.stamp = `${rec.replay ? 'REPLAY · ' : ''}${rec.cache || ''} · ${fmtB(rec.bytes)} · ${localHM(rec.at)}`; st.reveal.stampColor = rec.cache === 'HIT' ? 'cobalt' : rec.cache === 'MISS' ? 'vermilion' : 'amber' } master?.invalidate() }
  const tl = g.timeline({ onComplete: done })
  if (rec?.cache === 'HIT') tl.to(st.reveal, { p: 1, duration: 0.7, ease: 'power2.out', onUpdate: up })
  else if (rec?.cache === 'MISS') tl.to(st.reveal, { p: 0.38, duration: 0.5, ease: 'power1.inOut', onUpdate: up }).to(st.reveal, { p: 1, duration: 0.9, ease: 'power1.inOut', onUpdate: up }, '+=0.4')
  else tl.to(st.reveal, { p: 1, duration: 1.3, ease: 'none', onUpdate: up })
}
let replayIdx = 0
const ambient = () => {
  if (!open.value) return
  const rec = store.recent.length ? { ...store.recent[replayIdx++ % store.recent.length], replay: true } : null
  if (st.reveal.image && !busy && !st.redeem.verifying) void develop(rec)
  ambientTimer = window.setTimeout(ambient, 6000 + Math.random() * 2000)
}

/* ── 渲染循环 ── */
const canvasFor = (t) => ({ Free: cvFree.value, Plus: cvPlus.value, Pro: cvPro.value, Ultra: cvUltra.value })[t]
const ensureRenderer = async (t) => {
  if (R[t]) return R[t]
  if (t === 'Free') R[t] = new AsciiRenderer(cvFree.value, master, st)
  else if (t === 'Plus') R[t] = plusStyle === 'plot' ? new PlotterRenderer(cvPlus.value, master, st) : new DotMatrixRenderer(cvPlus.value, master, st)
  else if (t === 'Pro') R[t] = new BeadRenderer(cvPro.value, master, st)
  else { const pr = new ParticleRenderer(cvUltra.value, master, st, ovUltra.value); await pr.init(); R[t] = pr }
  return R[t]
}
const frame = (ms) => {
  if (!open.value) return
  const t = (ms - t0) / 1000; const dt = Math.min(0.05, t - last || 0.016); last = t
  if (!document.hidden) {
    const pv = pointer.inside ? pointer : null
    R[view.value]?.render(t, dt, pv)
    const inc = stackEl.value?.querySelector('.incoming'); if (inc) { const tt = inc.dataset.tier; R[tt]?.render(t, dt, pv) }
  }
  raf = requestAnimationFrame(frame)
}

/* ── 版本切换：旧档冻结成快照，新档被一条显影线从左到右显出来 ── */
const switchView = async (t, { force = false, instant = false, sweep = false } = {}) => {
  if (!open.value || busy || (t === view.value && !force)) return
  const from = view.value; const snap = snapEl.value; const src = canvasFor(from)
  await ensureRenderer(t)
  view.value = t; syncFromStore(); st.reveal.p = 1
  if (t === 'Ultra') { dark.value = true; st.dark = true } else if (from === 'Ultra' || t !== 'Ultra') { dark.value = false; st.dark = false }
  if (instant || st.reduced) return
  busy = true
  const dst = canvasFor(t); const g = await gsap()
  snap.width = src.width; snap.height = src.height
  const sx = snap.getContext('2d'); sx.drawImage(src, 0, 0)
  const band = st.connected && st.viewPlan ? (WIN.r1 * CH / CARD_H) * 100 : 0
  if (band > 0) { const k = snap.height / CARD_H; sx.clearRect(0, WIN.r1 * CH * k, snap.width, snap.height) }   // 旧卡只留图区
  snap.classList.add('on')
  dst.classList.add('incoming'); dst.dataset.tier = t; R[t].render(0, 0.016, null)
  const line = lineEl.value; const s = { x: 0 }
  await new Promise((res) => g.timeline({ onComplete: () => { snap.classList.remove('on'); dst.classList.remove('incoming'); dst.style.clipPath = ''; if (t === 'Ultra') ovUltra.value.style.clipPath = ''; line.style.opacity = 0; busy = false; res() } })
    .set(line, { opacity: sweep ? 0 : 1, left: 0 })
    .to(s, { x: 100, duration: 1.05, ease: 'power2.inOut', onUpdate: () => {
      /* 数据带整条立刻是新的，只让图区被显影线扫过——否则扫到一半会读到「新数字 + 旧量程」 */
      dst.style.clipPath = band > 0
        ? `polygon(0% 0%, ${s.x}% 0%, ${s.x}% ${band}%, 100% ${band}%, 100% 100%, 0% 100%)`
        : `inset(0 ${100 - s.x}% 0 0)`
      if (t === 'Ultra') ovUltra.value.style.clipPath = dst.style.clipPath
      line.style.left = s.x + '%'
    } }))
}

/* ── 兑换：图像下方的输入框 ── */
const say = (text, { err = false, ok = false } = {}) => { msg.value = text; msgErr.value = err; msgOk.value = ok; msgKey.value++; window.clearTimeout(msgTimer); msgTimer = window.setTimeout(() => { msg.value = '' }, 5000) }
const onInput = () => { const el = inputEl.value; const { code } = normalizeRedeemCode(el.value); st.redeem.text = code; const caretEnd = el.selectionEnd === el.value.length; el.value = code.replace(/(.{4})(?=.)/g, '$1-'); if (caretEnd) el.setSelectionRange(el.value.length, el.value.length); ready.value = code.length === 20; codeLen.value = code.length }
const onPaste = (e) => { const t = (e.clipboardData || window.clipboardData)?.getData('text'); if (t) { e.preventDefault(); inputEl.value.value = t; onInput() } }
const ERR = { invalid_config: '服务端没能校验本机的微信配置（wxcdn 返回 invalid_config）', account_unresolved: '找不到这个账号的本机微信数据目录', invalid_redeem_code: '兑换码无效，请核对后重试', redeem_code_used: '这个兑换码已经被使用过了', redeem_code_expired: '这个兑换码已过期', redeem_code_revoked: '这个兑换码已被撤销', plan_not_upgraded: '当前永久权益已覆盖此码，兑换码未被使用', account_frozen: '账号已被冻结，请联系管理员', config_unreadable: '读不到本机微信配置，无法签发凭证', invalid_token: '凭证失效，正在重新签发' }
const submitCode = async () => {
  const code = st.redeem.text
  if (code.length < 20) { const g = await gsap(); g.fromTo(inputEl.value, { x: 0 }, { x: 3, duration: 0.04, yoyo: true, repeat: 3 }); return }
  if (busy || verifying.value || locked.value) return
  verifying.value = true; st.redeem.verifying = true
  const t0v = performance.now(); const prevTier = tier.value
  try {
    const res = await store.redeem(selectedAccount.value, code)
    await new Promise((r) => setTimeout(r, Math.max(0, 700 - (performance.now() - t0v))))
    verifying.value = false; st.redeem.verifying = false; st.redeem.text = ''; inputEl.value.value = ''; ready.value = false; codeLen.value = 0; syncFromStore()
    const plan = res?.redemption?.plan, months = res?.redemption?.durationMonths
    const now = tier.value
    const label = `${String(plan || now).toUpperCase()}${months ? ` · ${months} 个月 · 至 ${localDate(store.snapshot?.account?.proExpiresAt || nowSec())}` : ' · 永久'}`
    if (now && now !== prevTier) { void sweepGlimm(null, { dark: dark.value || now === 'Ultra' }); await switchView(now, { force: true, sweep: true }); say(`已兑换 · ${label}`, { ok: true }) }
    else { void sweepGlimm(null, { dark: dark.value }); say(plan === 'Pro' && now === 'Pro' ? `已顺延 · +${months} 个月 · 至 ${localDate(store.snapshot?.account?.proExpiresAt || nowSec())}` : `已兑换 · ${label}`, { ok: true }) }
  } catch (e) {
    verifying.value = false; st.redeem.verifying = false; master?.invalidate()
    bad.value = false; await nextTick(); bad.value = true; window.setTimeout(() => { bad.value = false }, 1200)
    const code_ = e?.code || ''
    if (code_ === 'redeem_locked') { const until = Number(e?.detail?.lockedUntil || 0); if (until) st.lockedUntil = until; await store.refresh(selectedAccount.value); syncFromStore(); return say('连续失败太多次，兑换已锁定。只锁兑换，下载照常。', { err: true }) }
    if (code_ === 'rate_limited') return say(`操作太快，${e?.detail?.retryAfterSeconds || 7} 秒后可再试`, { err: true })
    const notSent = code_ === 'invalid_config' || code_ === 'account_unresolved' || code_ === 'config_unreadable' || code_ === 'account_frozen'
    say((notSent ? '兑换码没提交 · ' : '') + (ERR[code_] || e?.message || '没连上服务，码还在，稍后再试'), { err: code_ !== 'plan_not_upgraded' })   // 别让「接不进去」看着像「码是错的」
  }
}

/* ── 指针 ── */
const onPointerMove = (e) => { const r = stackEl.value.getBoundingClientRect(); pointer.x = (e.clientX - r.left) / r.width * CARD_W; pointer.y = (e.clientY - r.top) / r.height * CARD_H; pointer.inside = true }
const onPointerLeave = () => { pointer.inside = false; pointer.down = false }
const onPointerDown = () => { pointer.down = true; pointer.click = true }
const onPointerUp = () => { pointer.down = false }

/* ── 开关 ── */
const fit = () => { const w = window.innerWidth, h = window.innerHeight; scale.value = Math.min(0.78, (w - 24) / CARD_W, (h - 24) / (CARD_H + 56 + 150)) }
if (import.meta.dev) {
  window.__pwSweep = () => sweepGlimm(null, { dark: dark.value })
  window.__pwReveal = async (v) => { const g = await gsap(); g.killTweensOf(st.reveal); window.clearTimeout(ambientTimer); st.reveal.p = v; master?.invalidate() }
  window.__pwPlus = async (k = 'paint') => { plusStyle = k; try { R.Plus?.dispose() } catch (e) {} delete R.Plus; await ensureRenderer('Plus'); if (view.value === 'Plus') R.Plus.render(0, 0.016, null) }
  /* 截图用：停掉环境重播，把显影推到 100% 并盖一枚成交章 */
  window.__pwSettle = async (stampIdx = 0) => {
    const g = await gsap(); g.killTweensOf(st.reveal); window.clearTimeout(ambientTimer)
    const list = store.recent || []; const rec = list.length ? list[((list.length - 1 - stampIdx) % list.length + list.length) % list.length] : null
    st.reveal.p = 1
    if (rec) { st.reveal.stamp = `REPLAY · ${rec.cache} · ${fmtB(rec.bytes)} · ${localHM(rec.at)}`; st.reveal.stampColor = rec.cache === 'HIT' ? 'cobalt' : rec.cache === 'MISS' ? 'vermilion' : 'amber' }
    master?.invalidate()
  }
  /* mock 接入：__pwMock('Pro') 直接把契约形状的快照灌进 store；__pwMock('Pro', true) 连带播放兑换成功的光带与换档 */
  window.__pwMock = async (t = 'Pro', asRedeem = false) => {
    const now = nowSec(); const T = TIERS[t] || TIERS.Free
    const nextUtcDay = () => { const d = new Date(); return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + 1) / 1000 }
    const nextUtcMonth = () => { const d = new Date(); return Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1) / 1000 }
    const used = { Free: 13212672, Plus: 826781696, Pro: 13421772800, Ultra: 1407374883840 }[t]
    const quota = T.limit == null ? { period: 'lifetime', periodKey: 'lifetime', limitBytes: null, usedBytes: used, remainingBytes: null, resetsAt: null }
      : { period: T.period, periodKey: T.period === 'day' ? `day:${new Date().toISOString().slice(0, 10)}` : `month:${new Date().toISOString().slice(0, 7)}`, limitBytes: T.limit, usedBytes: used, remainingBytes: T.limit - used, resetsAt: T.period === 'day' ? nextUtcDay() : nextUtcMonth() }
    const account = { nickname: store.snapshot?.account?.nickname || '阿和', avatarUrl: null, plan: t, permanentPlan: t === 'Pro' ? 'Plus' : t, proExpiresAt: t === 'Pro' ? now + 177 * 86400 : null }
    const recent = [{ at: now - 1800, type: 'orig', bytes: 3565158, cache: 'MISS' }, { at: now - 900, type: 'orig', bytes: 2202009, cache: 'HIT' }, { at: now - 120, type: 'video', bytes: 50331648, cache: 'BYPASS' }]
    const prev = tier.value
    store.apply({ connected: true, account, quota, tokenExpiresAt: now + 2 * 86400 + 13 * 3600, tokenIssuedAt: now - 3600, quotaFetchedAt: now, quotaSource: 'quota', frozen: false, redeemLockedUntil: null, lastError: null, recent, enabled: true, tokenDuration: 'medium', wxid: 'mock' })
    syncFromStore()
    if (asRedeem && t !== prev) { void sweepGlimm(null, { dark: dark.value || t === 'Ultra' }); await switchView(t, { force: true, sweep: true }); say(`已兑换 · ${t.toUpperCase()}${t === 'Pro' ? ' · 6 个月 · 至 ' + localDate(account.proExpiresAt) : ' · 永久'}`, { ok: true }) }
    else await switchView(t, { instant: true })
  }
}
const close = () => closePlanWindow()
const start = async () => {
  await nextTick()
  st.reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches || false
  master = new CardMaster(st); R = {}
  try { await Promise.all(["italic 400 40px 'Instrument Serif'", "400 40px 'Instrument Serif'", "400 12px 'JetBrains Mono'", "400 8px 'Silkscreen'"].map((f) => document.fonts.load(f))) } catch (e) {}
  fit(); window.addEventListener('resize', fit)
  view.value = tier.value || 'Free'; st.redeem.text = ''; st.reveal.stamp = ''; msg.value = ''; ready.value = false; if (inputEl.value) inputEl.value.value = ''
  syncFromStore()
  await ensureRenderer(view.value)
  dark.value = view.value === 'Ultra'; st.dark = dark.value
  t0 = performance.now(); last = 0; raf = requestAnimationFrame(frame)
  tickTimer = window.setInterval(() => { if (!st.connected) syncFromStore(); else master?.invalidate() }, 1000)
  dlgEl.value?.focus({ preventScroll: true })
  void store.refresh(selectedAccount.value, { refresh: true }).then(() => { const nt = tier.value; if (nt && nt !== view.value) void switchView(nt, { instant: true }) })
  st.reveal.image = await loadImage(); master.invalidate()
  if (st.reveal.image) void develop(store.recent.length ? { ...store.recent[store.recent.length - 1], replay: true } : null)
  ambientTimer = window.setTimeout(ambient, 7000)
}
const stop = () => {
  cancelAnimationFrame(raf); raf = 0; window.clearInterval(tickTimer); window.clearTimeout(ambientTimer); window.removeEventListener('resize', fit)
  for (const k of Object.keys(R)) { try { R[k].dispose() } catch (e) {} } R = {}; master = null; busy = false; dark.value = false
}
watch(open, (v) => { if (v) void start(); else stop() })
onBeforeUnmount(stop)
</script>

<style>
/* 弹窗 = 索引条 + 一张满幅的卡。自绘颜色，不挂 theme-scope，深浅主题下一致；Ultra 熄灯。 */
.pw-scrim { position: fixed; inset: 0; z-index: 15000; display: grid; place-items: center; background: rgba(16, 15, 13, 0.46); }
.pw-dlg {
  --pw-diffuser: #EFEBE3; --pw-ink: #1B1917; --pw-ink-35: rgba(27,25,23,.35); --pw-cobalt: #2F5BEA; --pw-dark: #0E0C0B;
  position: relative; width: 644px; transform: scale(var(--pw-scale, .78)); transform-origin: center;
  border-radius: 12px; overflow: hidden; color: var(--pw-ink); background: var(--pw-diffuser);
  box-shadow: 0 40px 120px rgba(0,0,0,.45); transition: background 1.2s ease; outline: none;
  font-family: "Instrument Sans", -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
}
.pw-dlg.is-dark { background: var(--pw-dark); color: #E9E2D2; }
.pw-grain { position: absolute; inset: -10%; pointer-events: none; opacity: .045; mix-blend-mode: multiply; z-index: 4;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 .9 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>"); }
.pw-dlg.is-dark .pw-grain { mix-blend-mode: screen; opacity: .06; }
.pw-index { position: relative; display: grid; grid-template-columns: repeat(4, 1fr); height: 56px; z-index: 8; }
.pw-tier { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px; font-family: "Instrument Serif", "Times New Roman", "Songti SC", serif; font-style: italic; font-size: 26px; line-height: 1; letter-spacing: -.01em; color: var(--pw-ink-35); position: relative; transition: color .35s; cursor: pointer; background: none; border: 0; padding: 0; }
.pw-tier:hover, .pw-tier.view { color: var(--pw-ink); }
.pw-tier:focus-visible { outline: 1.5px solid var(--pw-cobalt); outline-offset: -4px; }
.pw-tier .w::before { content: ""; display: inline-block; width: 5px; height: 5px; border-radius: 50%; background: transparent; margin-right: 9px; vertical-align: 4px; }
.pw-tier.cur .w::before { background: var(--pw-cobalt); }
.pw-tier small { font-family: "JetBrains Mono", "SF Mono", ui-monospace, Menlo, monospace; font-style: normal; font-size: 8.5px; letter-spacing: .12em; color: rgba(27,25,23,.55); }
.pw-tier.cur small { color: var(--pw-cobalt); }
.pw-tier::after { content: ""; position: absolute; left: 22%; right: 22%; bottom: 0; height: 1px; background: currentColor; transform: scaleX(0); transition: transform .35s cubic-bezier(.16,1,.3,1); }
.pw-tier:hover::after, .pw-tier.view::after { transform: scaleX(1); }
.pw-dlg.is-dark .pw-tier { color: rgba(233,226,210,.35); } .pw-dlg.is-dark .pw-tier.view, .pw-dlg.is-dark .pw-tier:hover { color: #E9E2D2; } .pw-dlg.is-dark .pw-tier small { color: rgba(233,226,210,.55); } .pw-dlg.is-dark .pw-tier.cur small { color: var(--pw-cobalt); }
.pw-stack { position: relative; width: 644px; height: 407px; }
.pw-stack canvas { position: absolute; left: 0; top: 0; width: 644px; height: 407px; display: none; }
.pw-stack canvas.active, .pw-stack canvas.incoming, .pw-stack canvas.snap-cv.on, .pw-stack canvas.overlay.on { display: block; }
.pw-stack canvas.snap-cv { z-index: 2; }
.pw-stack canvas.incoming { z-index: 3; clip-path: inset(0 100% 0 0); }
.pw-stack canvas.overlay { pointer-events: none; z-index: 3; }
.pw-line { position: absolute; top: 0; bottom: 0; width: 6px; left: 0; z-index: 4; pointer-events: none; opacity: 0; background: var(--pw-ink); mix-blend-mode: difference; }
.pw-intro { position: relative; z-index: 8; margin: 0; padding: 14px 24px 10px; text-align: center; font-size: 16px; font-weight: 500; line-height: 1.45; letter-spacing: .03em; color: #B07A20; }
.pw-contact { padding: 0; border: 0; background: none; color: inherit; font: inherit; text-decoration: underline; text-underline-offset: 3px; cursor: pointer; }
.pw-dlg.is-dark .pw-intro { color: #F0D391; }
.pw-dlg.is-dark .pw-line { background: #fff; mix-blend-mode: normal; }
.pw-enter-active, .pw-leave-active { transition: opacity .22s ease; }
.pw-enter-from, .pw-leave-to { opacity: 0; }
@media (prefers-reduced-motion: reduce) { .pw-dlg { transition: none; } }
</style>
