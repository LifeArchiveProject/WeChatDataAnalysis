import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

// AI Elements Vue 按需源码共用的样式合并入口。
export const cn = (...values: ClassValue[]) => twMerge(clsx(values))
