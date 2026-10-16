import type { LanguageModelUsage } from 'ai'
import type { ComputedRef, InjectionKey } from 'vue'
import { inject } from 'vue'

export type ModelId = string

export interface ContextContextValue {
  usedTokens: ComputedRef<number>
  maxTokens: ComputedRef<number>
  usage: ComputedRef<LanguageModelUsage | undefined>
  modelId: ComputedRef<ModelId | undefined>
}

export const ContextKey: InjectionKey<ContextContextValue>
  = Symbol('ContextContext')

export function useContextValue(): ContextContextValue {
  const context = inject<ContextContextValue>(ContextKey)
  if (!context) {
    throw new Error('Context components must be used within Context')
  }
  return context
}
