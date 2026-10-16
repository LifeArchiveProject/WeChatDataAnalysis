import { openMessageExternalUrl } from '~/lib/chat/message-links'

// 购买联系渠道的跳转地址和提示文案。
const DEVELOPER_CONTACT_URL = 'https://t.me/knchudj'
const DEVELOPER_GROUP_URL = 'https://t.me/+IQKBDeXtaKozZWYx'

export const DEVELOPER_CONTACT_TITLE = '购买联系'
export const DEVELOPER_CONTACT_LABEL = DEVELOPER_CONTACT_URL
export const DEVELOPER_CONTACT_HINT = '或者加入 TG 群私聊群所有者'

export const FEATURE_UNAVAILABLE_MESSAGE = '当前版本暂不支持此功能。'

export const openDeveloperContact = () => openMessageExternalUrl(DEVELOPER_CONTACT_URL)
export const openDeveloperGroup = () => openMessageExternalUrl(DEVELOPER_GROUP_URL)
