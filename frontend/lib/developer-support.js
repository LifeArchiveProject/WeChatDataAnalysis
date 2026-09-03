import { openMessageExternalUrl } from '~/lib/chat/message-links'

export const FEATURE_UNAVAILABLE_MESSAGE = '当前版本仅展示该功能入口，暂时无法执行。请添加 QQ 3434549571（备注「高级版」）联系开发者获取支持。'

export const openDeveloperContact = () => openMessageExternalUrl('https://wpa.qq.com/msgrd?v=3&uin=3434549571&site=qq&menu=yes')
