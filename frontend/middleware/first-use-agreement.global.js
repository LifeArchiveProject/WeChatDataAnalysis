import { isFirstUseAgreementAccepted } from '~/lib/first-use-agreement'

export default defineNuxtRouteMiddleware((to) => {
  if (import.meta.server || useNuxtApp().isHydrating || to.path === '/agreement') return
  if (isFirstUseAgreementAccepted()) return

  return navigateTo({
    path: '/agreement',
    query: { redirect: to.fullPath || '/' }
  }, { replace: true })
})
