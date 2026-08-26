import { openMessageExternalUrl } from '~/lib/chat/message-links'

export const FEATURE_UNAVAILABLE_MESSAGE = '当前版本仅展示该功能入口，暂时无法执行。请加入 QQ 交流群，并在群内联系开发者获取支持。'

export const openDeveloperGroup = () => openMessageExternalUrl('https://qm.qq.com/q/VQEQ7PcGkk')
