import { defineStore } from 'pinia'

/**
 * WxCDN 套餐/额度状态（镜像后端 GET /api/cdn/plan 的快照）。
 * 真值来自 Worker（/token /quota /redeem /download 头），前端只读快照，不自算额度。
 */
export const useCdnPlanStore = defineStore('cdnPlan', () => {
  const snapshot = ref(null)          // 后端 get_plan_snapshot() 原样
  const loading = ref(false)
  const error = ref(null)             // {code, message, retryAfterSeconds?}
  const fetchedAt = ref(0)
  const account = ref('')

  const connected = computed(() => !!snapshot.value?.connected && !!snapshot.value?.account)
  const plan = computed(() => (connected.value ? { account: snapshot.value.account, quota: snapshot.value.quota } : null))
  const tier = computed(() => String(snapshot.value?.account?.plan || '') || null)
  const frozen = computed(() => !!snapshot.value?.frozen)
  const lockedUntil = computed(() => Number(snapshot.value?.redeemLockedUntil || 0))
  const recent = computed(() => (Array.isArray(snapshot.value?.recent) ? snapshot.value.recent : []))
  const exhausted = computed(() => {
    const q = snapshot.value?.quota
    if (!q || q.limitBytes == null) return false
    if (Number(q.remainingBytes) <= 0) return true
    const le = snapshot.value?.lastError
    return !!(le && le.code === 'quota_exceeded' && q.resetsAt && q.resetsAt > Date.now() / 1000)
  })

  const apply = (snap) => { snapshot.value = snap && typeof snap === 'object' ? snap : null; error.value = snap?.error || null; fetchedAt.value = Date.now() }

  const refresh = async (acc, { refresh = false } = {}) => {
    const api = useApi(); const a = String(acc || '').trim(); if (!a) { snapshot.value = null; return null }
    account.value = a; loading.value = true
    try { const res = await api.getCdnPlan(a, { refresh }); apply(res); return res }
    catch (e) { error.value = { code: e?.code || 'network', message: e?.message || '连不上本地服务' }; return null }
    finally { loading.value = false }
  }
  const connect = async (acc) => { const api = useApi(); const a = String(acc || account.value || '').trim(); const res = await api.connectCdn(a); apply(res); return res }
  const redeem = async (acc, code) => { const api = useApi(); const a = String(acc || account.value || '').trim(); const res = await api.redeemCdnCode(a, code); if (res?.snapshot) apply(res.snapshot); return res }

  return { snapshot, loading, error, fetchedAt, account, connected, plan, tier, frozen, lockedUntil, recent, exhausted, refresh, connect, redeem, apply }
})
