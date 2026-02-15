#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
生成 wechat_db_config.json:
- 读取 wechat_db_config_template.json
- 融合本项目 analyze_wechat_databases 的启发式 + ohmywechat 常见字段/消息类型
- 批量为每个表字段补全中文含义，并写出 wechat_db_config.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime
import sys

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "wechat_db_config_template.json"
OUTPUT_MAIN = ROOT / "wechat_db_config.json"
OUTPUT_DIR = ROOT / "output" / "configs"
OUTPUT_COPY = OUTPUT_DIR / "wechat_db_config.generated.json"

# 允许从 tools/ 目录运行时仍能 import 根目录模块
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 尝试导入分析器以复用其启发式
AnalyzerCls = None
try:
    from analyze_wechat_databases import WeChatDatabaseAnalyzer  # type: ignore
    AnalyzerCls = WeChatDatabaseAnalyzer
except Exception:
    AnalyzerCls = None


def build_db_descriptions() -> dict[str, str]:
    return {
        "message": "聊天记录核心数据库",
        # message_{n}.db 会在 fill_config 里按正则单独处理（分片/分表）
        "message_fts": "聊天消息全文索引数据库（FTS）",
        "message_resource": "消息资源索引数据库（图片/文件/视频等）",
        "contact": "联系人数据库（好友/群/公众号基础信息）",
        "session": "会话数据库（会话列表与未读统计）",
        "sns": "朋友圈数据库（动态与互动）",
        "favorite": "收藏数据库",
        "favorite_fts": "收藏全文索引数据库（FTS）",
        "emoticon": "表情包数据库",
        "head_image": "头像数据数据库",
        "hardlink": "硬链接索引数据库（资源去重/快速定位）",
        "media_0": "媒体数据数据库（含语音SILK等）",
        "unspportmsg": "不支持消息数据库（客户端不支持的消息类型）",
        "general": "通用/系统数据库（新消息通知/支付等）",
        "contact_fts": "联系人全文索引数据库（FTS）",
        "chat_search_index": "（本项目生成）聊天记录全文检索索引库（FTS5，用于搜索）",
        "bizchat": "公众号/企业微信相关数据库（会话/联系人等）",
        "digital_twin": "（本项目生成）数字分身数据库（派生数据，非微信原始库）",
    }


def build_message_types_from_ohmywechat() -> dict[str, str]:
    """
    参考 ohmywechat 等资料补充 PC/公众号常见 local_type → 含义
    使用 (Type,SubType) 形式的字符串键；子类型未知时置 0
    """
    return {
        "1,0": "文本消息",
        "3,0": "图片消息",
        "34,0": "语音消息",
        "42,0": "名片消息",
        "43,0": "视频消息",
        "47,0": "动画表情",
        "48,0": "位置消息",
        "244813135921,0": "引用消息",
        "17179869233,0": "卡片式链接（带描述）",
        "21474836529,0": "卡片式链接/图文消息（公众号，mmreader XML）",
        "154618822705,0": "小程序分享",
        "12884901937,0": "音乐卡片",
        "8594229559345,0": "红包卡片",
        "81604378673,0": "聊天记录合并转发消息",
        "266287972401,0": "拍一拍消息",
        "8589934592049,0": "转账卡片",
        "270582939697,0": "视频号直播卡片",
        "25769803825,0": "文件消息",
        "10000,0": "系统消息（撤回/入群提示等）",
    }


KNOWN_FIELD_MEANINGS = {
    # 通用主键/标识
    "id": "标识符字段（主键/索引）",
    "local_id": "本地自增ID（主键/定位用）",
    "server_id": "服务器消息ID（唯一且全局递增）",
    "svr_id": "服务器消息ID（同server_id）",
    "message_id": "消息ID（表内主键或消息级索引）",
    "resource_id": "资源ID（资源明细主键）",
    "history_id": "历史消息ID（系统消息/历史消息关联键）",

    # 会话/用户/群聊
    "username": "用户名/会话标识（wxid_xxx 或 xxx@chatroom）",
    "user_name": "用户名/会话标识（wxid_xxx 或 xxx@chatroom）",
    "sender_id": "发送者内部ID（与Name2Id映射）",
    "real_sender_id": "真实发送者ID（群聊内消息具体成员）",
    "chat_id": "会话内部ID（与ChatName2Id映射）",
    "chat_name_id": "会话内部ID（与ChatName2Id映射）",
    "session_id": "会话ID（FTS/资源维度的会话映射）",
    "session_name": "会话名（username 文本值）",
    "session_name_id": "会话内部ID（username 的数值映射）",
    "talker_id": "会话/房间ID（Name2Id 对照）",

    # 消息结构/状态
    "local_type": "本地消息类型（local_type）",
    "type": "类型标识（上下文相关：消息/表情/配置）",
    "sub_type": "子类型标识（同一主类型细分）",
    "status": "状态标志位（发送/接收/已读/撤回等）",
    "upload_status": "上传状态（媒体/资源上行状态）",
    "download_status": "下载状态（媒体/资源下行状态）",
    "server_seq": "服务器序列号（消息顺序校验）",
    "origin_source": "消息来源标识（客户端/转发/系统）",
    "source": "来源附加信息（XML/JSON 等）",
    "msg_status": "消息状态（扩展）",

    # 消息内容
    "message_content": "消息内容（部分类型为zstd压缩的XML：mmreader）",
    "compress_content": "压缩内容（多见zstd，可能存放富文本XML）",
    "packed_info_data": "打包扩展信息（二进制，消息元数据）",
    "packed_info": "打包扩展信息（二进制/文本混合）",
    "data_index": "数据分片/索引（媒体片段定位）",

    # 时间
    "create_time": "创建时间（Unix时间戳，秒）",
    "last_update_time": "最后更新时间（Unix时间戳）",
    "last_modified_time": "最后修改时间（Unix时间戳）",
    "update_time": "更新时间（Unix时间戳）",
    "invalid_time": "失效时间（Unix时间戳）",
    "access_time": "访问时间（Unix时间戳）",
    "last_timestamp": "最后消息时间（会话）",
    "sort_timestamp": "排序时间（会话排序）",
    "timestamp": "时间戳（Unix时间戳）",

    # 排序/去重
    "sort_seq": "排序序列（单会话内消息排序/去重）",
    "server_seq_": "服务器序列号（扩展）",

    # 联系人/群聊
    "alias": "别名（用户自定义标识）",
    "encrypt_username": "加密用户名",
    "flag": "标志位（多用途：联系人/公众号/配置）",
    "delete_flag": "删除标志（软删除）",
    "verify_flag": "认证标志（公众号/企业认证等）",
    "remark": "备注名",
    "remark_quan_pin": "备注名全拼",
    "remark_pin_yin_initial": "备注名拼音首字母",
    "nick_name": "昵称",
    "pin_yin_initial": "昵称拼音首字母",
    "quan_pin": "昵称全拼",
    "description": "描述/个性签名/备注",
    "extra_buffer": "扩展缓冲区（二进制/序列化）",
    "ext_buffer": "扩展缓冲区（二进制/序列化）",
    "ext_buffer_": "扩展缓冲区（二进制/序列化）",
    "chat_room_type": "群类型标志",
    "owner": "群主 username",

    # 头像/媒体
    "big_head_url": "头像大图URL",
    "small_head_url": "头像小图URL",
    "head_img_md5": "头像MD5",
    "image_buffer": "头像二进制数据",
    "voice_data": "语音二进制数据（多为SILK）",

    # FTS / 内部表
    "acontent": "FTS检索内容（分词后文本）",
    "block": "FTS内部块数据（二进制）",
    "segid": "FTS分段ID",
    "term": "FTS分词条目",
    "pgno": "FTS页号",
    "c0": "FTS列c0（内部结构）",
    "c1": "FTS列c1（内部结构）",
    "c2": "FTS列c2（内部结构）",
    "c3": "FTS列c3（内部结构）",
    "c4": "FTS列c4（内部结构）",
    "c5": "FTS列c5（内部结构）",
    "c6": "FTS列c6（内部结构）",
    "c7": "FTS列c7（内部结构）",
    "c8": "FTS列c8（内部结构）",
    "c9": "FTS列c9（内部结构）",
    "c10": "FTS列c10（内部结构）",
    "c11": "FTS列c11（内部结构）",
    "c12": "FTS列c12（内部结构）",
    "sz": "FTS文档大小信息",
    "_rowid_": "SQLite内部行ID",

    # 资源/硬链接
    "md5": "资源MD5",
    "md5_hash": "MD5哈希整数映射（快速索引）",
    "file_name": "文件名（相对/逻辑名）",
    "file_size": "文件大小（字节）",
    "dir1": "资源路径一级目录编号（分桶）",
    "dir2": "资源路径二级目录编号（分桶）",
    "modify_time": "文件修改时间戳",

    # 会话统计
    "unread_count": "未读计数",
    "unread_first_msg_srv_id": "会话未读区间首个消息SvrID",
    "is_hidden": "会话隐藏标志",
    "summary": "会话摘要（最近消息摘要）",
    "draft": "草稿内容",
    "status_": "状态/标志（上下文）",
    "last_clear_unread_timestamp": "上次清空未读时间",
    "last_msg_locald_id": "最后一条消息的本地ID（拼写原样保留）",
    "last_msg_type": "最后一条消息类型",
    "last_msg_sub_type": "最后一条消息子类型",
    "last_msg_sender": "最后一条消息发送者username",
    "last_sender_display_name": "最后一条消息发送者显示名",
    "last_msg_ext_type": "最后一条消息扩展类型",

    # 常见“Key-Value”配置表（多库复用）
    "key": "键（Key-Value配置表）",
    "valueint64": "整数值（int64）",
    "valuedouble": "浮点值（double）",
    "valuestdstr": "字符串值（std::string）",
    "valueblob": "二进制值（blob）",
    "k": "配置键（k）",
    "v": "配置值（v）",

    # 常见保留字段
    "reserved0": "保留字段（reserved0）",
    "reserved1": "保留字段（reserved1）",
    "reserved2": "保留字段（reserved2）",
    "reserved3": "保留字段（reserved3）",

    # 版本/位标志
    "version": "版本号（记录/结构版本，具体含义依表而定）",
    "bit_flag": "位标志/开关（bit flags）",

    # 本项目索引/缓存库常见字段
    "render_type": "渲染类型（本项目定义：text/image/system/...）",
    "db_stem": "来源数据库分片名（如 message_0）",
    "table_name": "来源表名（如 Msg_xxx）",
    "sender_username": "发送者username（解码后）",
    "preview": "会话预览文本（用于会话列表展示）",
    "built_at": "构建时间（Unix时间戳，秒）",
    "tablename": "表名（tableName）",
    "value": "值（value）",
    "brand_user_name": "品牌/公众号username（brand_user_name）",

    # 常见业务字段（命名自解释）
    "ticket": "票据/验证ticket（ticket）",
    "delete_table_name": "删除记录关联的消息表名（delete_table_name）",
    "res_path": "资源路径（res_path）",
    "biz_username": "公众号username（biz_username）",
    "search_key": "搜索键/索引字段（search_key）",
    "click_type": "点击/热词类型（click_type）",
    "a_group_remark": "群备注（FTS检索字段：a_group_remark）",
    "op_code": "操作码（op_code）",
    "query": "查询关键词（query）",
    "score": "评分/权重（score）",
    "keyword": "关键词（keyword）",
    "pay_load_": "payload/扩展数据（pay_load_）",
    "bill_no": "账单号（bill_no）",
    "session_title": "会话标题（session_title）",
    "unread_stat": "未读统计字段（unread_stat）",
    "ui_type": "UI类型/发布类型（ui_type）",
    "error_type": "错误类型（error_type）",
    "tips_content": "提示内容（tips_content）",
    "record_content": "记录内容（record_content）",
    "business_type": "业务类型（business_type）",
    "access_content_key": "访问内容key（access_content_key）",
    "access_content_type": "访问内容类型（access_content_type）",
    "range_type": "范围类型（range_type）",
    "message_local_type": "消息类型（message_local_type）",
    "message_origin_source": "消息来源标识（message_origin_source）",

    # 朋友圈（sns）常见拆分字段
    "tid_heigh_bit": "tid 高位拆分字段（heigh_bit，字段名原样保留）",
    "tid_low_bit": "tid 低位拆分字段（low_bit）",
    "break_flag": "断点/分页标志（0/1；用于分页/增量拉取水位）",

    # WCDB 压缩控制
    "WCDB_CT_message_content": "WCDB压缩标记（message_content列）",
    "WCDB_CT_source": "WCDB压缩标记（source列）",
}


# 表级字段含义覆盖（优先级高于 KNOWN_FIELD_MEANINGS）
# key: table_name.lower() ; value: { field_name.lower(): meaning }
KNOWN_FIELD_MEANINGS_BY_TABLE: dict[str, dict[str, str]] = {
    # contact.db
    "contact": {
        "id": "序号（通常与 name2id.rowid 对应）",
        "username": "联系人的 wxid / 群聊 username（可唯一确定联系人）",
        "local_type": "联系人类型：1=通讯录好友/公众号/已添加群聊；2=未添加到通讯录的群聊；3=群中的陌生人；5=企业微信好友；6=群聊中的陌生企业微信好友",
        "alias": "微信号（微信里显示的微信号）",
        "flag": "联系人标志位（需转二进制；常见：第7位星标，第12位置顶，第17位屏蔽朋友圈，第24位仅聊天）",
        "head_img_md5": "头像md5（可通过 head_image.db 查询对应头像）",
        "verify_flag": "认证标志（公众号/企业等；非0常表示公众号）",
        "description": "描述字段（样本为空；用途待确认）",
        "extra_buffer": "好友扩展信息（protobuf；包含性别/地区/签名等，本项目解析 gender/signature/country/province/city/source_scene）",
        "chat_room_notify": "群消息通知相关设置（样本为0/1；疑似免打扰/通知开关，待确认）",
        "is_in_chat_room": "群聊状态标记（样本为1/2；具体含义待确认）",
        "chat_room_type": "群聊类型/标志（样本为0/2；具体含义待确认）",
    },
    "stranger": {
        "id": "序号（通常与 name2id.rowid 对应）",
        "username": "联系人的 wxid / 群聊 username",
        "local_type": "联系人类型：1=通讯录好友/公众号/已添加群聊；2=未添加到通讯录的群聊；3=群中的陌生人；5=企业微信好友；6=群聊中的陌生企业微信好友",
        "alias": "微信号（微信里显示的微信号）",
        "flag": "联系人标志位（需转二进制；常见：第7位星标，第12位置顶，第17位屏蔽朋友圈，第24位仅聊天）",
        "head_img_md5": "头像md5（可通过 head_image.db 查询对应头像）",
        "verify_flag": "认证标志（公众号/企业等；非0常表示公众号）",
        "description": "描述字段（样本为空；用途待确认）",
        "extra_buffer": "好友扩展信息（protobuf；包含性别/地区/签名等，本项目解析 gender/signature/country/province/city/source_scene）",
        "chat_room_notify": "群消息通知相关设置（样本为0/1；疑似免打扰/通知开关，待确认）",
        "is_in_chat_room": "群聊状态标记（样本为1/2；具体含义待确认）",
        "chat_room_type": "群聊类型/标志（样本为0/2；具体含义待确认）",
    },
    "biz_info": {
        "id": "序号（与 name2id.rowid 对应，可唯一确定一个公众号）",
        "username": "公众号username（原始 wxid/gh_xxx）",
        "type": "公众号类型：1=公众号，0=订阅号（资料来源：万字长文）",
        "accept_type": "接收类型（accept_type；含义待确认，样本常为0）",
        "child_type": "子类型（child_type；含义待确认，样本常为0）",
        "version": "版本号（含义待确认，样本常为0）",
        "external_info": "公众号详细信息（常见 JSON；含底部菜单/交互配置等）",
        "brand_info": "公众号品牌/菜单信息（常见 JSON：urls 等）",
        "brand_list": "品牌列表/关联列表（格式待确认，可能为 JSON）",
        "brand_flag": "品牌/能力标志位（含义待确认）",
        "belong": "归属字段（含义待确认）",
        "home_url": "主页链接（含义待确认）",
    },
    "chat_room": {
        "id": "序号（与 name2id.rowid 对应）",
        "username": "群聊的username（xxx@chatroom）",
        "owner": "群主username",
        "ext_buffer": "群成员username与群昵称（protobuf：ChatRoomData.members 等）",
    },
    "chat_room_info_detail": {
        "room_id_": "序号（与 name2id.rowid 对应）",
        "username_": "群聊的username（xxx@chatroom）",
        "announcement_": "群公告（文本）",
        "announcement_editor_": "群公告编辑者username",
        "announcement_publish_time_": "群公告发布时间（时间戳）",
        "chat_room_status_": "群状态/标志位（bitmask；样本常见 0x80000 等，具体位含义待确认）",
        "xml_announcement_": "群公告（XML，可解析更多信息：图片/文件等）",
        "ext_buffer_": "扩展信息（protobuf-like；样本长度较小，具体结构待确认）",
    },
    "chatroom_member": {
        "room_id": "群聊ID（对应 name2id.rowid）",
        "member_id": "群成员ID（对应 name2id.rowid）",
    },
    "contact_label": {
        "label_id_": "标签ID",
        "label_name_": "标签名称",
        "sort_order_": "排序",
    },

    # message_*.db / biz_message_*.db
    "msg_*": {
        "local_id": "自增id（本地）",
        "server_id": "服务端id（每条消息唯一）",
        "local_type": "消息类型（local_type；低32位=type，高32位=sub_type；可用 (local_type & 0xFFFFFFFF) 与 (local_type >> 32) 拆分）",
        "sort_seq": "排序字段（单会话内消息排序；样本≈create_time*1000）",
        "real_sender_id": "发送者id（可通过 Name2Id.rowid 映射到 username）",
        "create_time": "秒级时间戳",
        "server_seq": "服务端接收顺序id（server_seq）",
        "message_content": "消息内容：local_type=1 时为文本，其它类型多为 Zstandard 压缩后的XML/二进制",
        "compress_content": "压缩后的内容（多见 Zstandard）",
        "packed_info_data": "protobuf扩展信息（图片文件名/语音转文字/合并转发文件夹名等）",
    },
    "name2id": {
        "is_session": "是否会话名标记（1=会话/聊天对象；0=其它映射，如群成员ID）",
    },

    # session.db
    "sessiontable": {
        "type": "会话类型（样本为0；枚举待确认）",
        "status": "会话状态（样本为0；枚举待确认）",
        "unread_first_pat_msg_local_id": "未读拍一拍消息的本地ID（样本为0；含义待确认）",
        "unread_first_pat_msg_sort_seq": "未读拍一拍消息的排序序号（样本为0；含义待确认）",
    },
    "session_last_message": {
        "username": "会话username",
        "sort_seq": "最后一条消息sort_seq",
        "local_id": "最后一条消息local_id",
        "create_time": "最后一条消息create_time（秒级时间戳）",
        "local_type": "最后一条消息local_type",
        "sender_username": "最后一条消息发送者username",
        "preview": "最后一条消息预览文本（用于会话列表）",
        "db_stem": "来源消息库分片名（如 message_0）",
        "table_name": "来源消息表名（如 Msg_xxx）",
        "built_at": "构建时间（Unix时间戳，秒）",
    },

    # 本项目 chat_search_index.db
    "message_fts": {
        "text": "可检索文本（索引内容）",
        "render_type": "渲染类型（text/system/image/voice/video/emoji/...，本项目定义）",
        "db_stem": "来源消息库分片名（如 message_0）",
        "table_name": "来源消息表名（如 Msg_xxx）",
        "sender_username": "发送者username（解码后）",
    },

    # emoticon.db
    "knonstoreemoticontable": {
        "type": "表情类型（样本均为3；枚举含义待确认）",
        "caption": "表情说明/标题（caption）",
        "product_id": "表情包/产品ID（product_id）",
        "aes_key": "AES密钥（用于CDN下载解密）",
        "auth_key": "鉴权key（CDN下载）",
        "extern_md5": "外部资源md5（extern_md5）",
    },
    "kstoreemoticonpackagetable": {
        "package_id_": "表情包ID（package_id）",
        "package_name_": "表情包名称",
        "payment_status_": "支付状态（payment_status）",
        "download_status_": "下载状态（download_status）",
        "install_time_": "安装时间（时间戳）",
        "remove_time_": "移除时间（时间戳）",
        "sort_order_": "排序",
        "introduction_": "简介（introduction）",
        "full_description_": "完整描述（full_description）",
        "copyright_": "版权信息",
        "author_": "作者信息",
        "store_icon_url_": "商店图标URL",
        "panel_url_": "面板/详情页URL",
    },
    "kstoreemoticonfilestable": {
        "package_id_": "表情包ID（package_id）",
        "md5_": "表情md5",
        "type_": "表情类型（type）",
        "sort_order_": "排序",
        "emoticon_size_": "表情文件大小（字节）",
        "emoticon_offset_": "表情文件偏移（用于包内定位）",
        "thumb_size_": "缩略图大小（字节）",
        "thumb_offset_": "缩略图偏移（用于包内定位）",
    },

    # favorite.db
    "fav_db_item": {
        "version": "版本号（收藏条目结构/内容版本；样本为87）",
        "fromusr": "来源用户username（收藏来源）",
        "realchatname": "来源群聊username（若收藏来源于群聊）",
        "upload_error_code": "上传错误码",
        "trans_res_error_code": "资源转换错误码（trans_res_error_code）",
    },

    # general.db
    "ilink_voip": {
        "wx_chatroom_": "群聊username（xxx@chatroom）",
        "millsecond_": "毫秒时间戳/时间标记（字段名推断）",
        "group_id_": "ILink group_id（字段名推断）",
        "room_id_": "房间ID（字段名推断）",
        "room_key_": "房间key（字段名推断）",
        "route_id_": "路由ID（字段名推断）",
        "voice_status_": "通话状态（字段名推断）",
        "talker_create_user_": "发起者username（字段名推断）",
        "not_friend_user_list_": "非好友成员列表（字段名推断）",
        "members_": "成员列表（字段名推断）",
        "is_ilink_": "是否ilink通话（字段名推断）",
        "ever_quit_chatroom_": "是否曾退出群聊（字段名推断）",
    },
    "fmessagetable": {
        "user_name_": "用户名（好友验证/陌生人会话用户名）",
        "type_": "消息类型（好友验证/系统消息；样本为37）",
        "timestamp_": "时间戳",
        "encrypt_user_name_": "加密用户名",
        "content_": "内容（验证消息/系统提示等）",
        "is_sender_": "是否发送方（is_sender）",
        "ticket_": "票据/验证ticket",
        "scene_": "来源场景码（scene）",
        "fmessage_detail_buf_": "详细信息（protobuf-like；包含验证文案/来源等信息）",
    },
    "handoff_remind_v0": {
        "item_id": "条目ID（item_id）",
        "head_icon": "图标（URL/资源标识）",
        "title": "标题",
        "desc_type": "描述类型（desc_type）",
        "create_time": "创建时间（时间戳）",
        "start_time": "开始时间（时间戳）",
        "expire_time": "过期时间（时间戳）",
        "biz_type": "业务类型（biz_type）",
        "version": "版本号（version）",
        "url": "跳转URL",
        "extra_info": "扩展信息（extra_info）",
    },
    "transfertable": {
        "transfer_id": "转账ID（transfer_id）",
        "transcation_id": "交易ID（transaction_id，原字段拼写保留）",
        "message_server_id": "关联消息server_id",
        "second_message_server_id": "关联第二条转账消息server_id（可在 message_*.db::Msg_* 表的 server_id 对应到）",
        "session_name": "会话username",
        "pay_sub_type": "支付子类型（pay_sub_type）",
        "pay_receiver": "收款方username",
        "pay_payer": "付款方username",
        "begin_transfer_time": "转账开始时间（时间戳）",
        "last_modified_time": "最后修改时间（时间戳）",
        "invalid_time": "失效时间（时间戳）",
        "last_update_time": "最后更新时间（时间戳）",
        "delay_confirm_flag": "延迟确认标志（delay_confirm_flag）",
        "bubble_clicked_flag": "气泡点击标志（bubble_clicked_flag）",
    },

    # bizchat.db
    "chat_group": {
        "brand_user_name": "品牌/公众号username（brand_user_name）",
        "bit_flag": "位标志/开关（bit_flag）",
        "chat_name": "群组名称（chat_name）",
        "user_list": "成员列表（常见为 ; 分隔的 user_id/username 列表；待确认）",
        "reserved0": "保留字段（reserved0）",
        "reserved1": "保留字段（reserved1）",
        "reserved2": "保留字段（reserved2）",
        "reserved3": "保留字段（reserved3）",
    },
    "user_info": {
        "brand_user_name": "品牌/公众号username（brand_user_name）",
        "bit_flag": "位标志/开关（bit_flag）",
        "reserved0": "保留字段（reserved0）",
        "reserved1": "保留字段（reserved1）",
        "reserved2": "保留字段（reserved2）",
        "reserved3": "保留字段（reserved3）",
    },

    # sns.db
    "snsmessage_tmp3": {
        "from_username": "来源用户username（评论/点赞发起者）",
        "from_nickname": "来源用户昵称（评论/点赞发起者）",
        "to_username": "目标用户username（被回复/被@的人）",
        "to_nickname": "目标用户昵称（被回复/被@的人）",
        "comment_flag": "评论标志位（样本为0；具体 bit 含义待确认）",
    },
    "snsadtimeline": {
        "ad_content": "广告内容（ad_content，格式待确认）",
        "remind_source_info": "提醒来源信息（remind_source_info，格式待确认）",
        "remind_self_info": "提醒自身信息（remind_self_info，格式待确认）",
        "extra_data": "扩展数据（extra_data，格式待确认）",
    },

    # unspportmsg.db
    "unsupportmessage": {
        "from_user": "发送者username",
        "to_user": "接收者username",
        "msg_source": "消息来源附加信息（msg_source）",
    },

    # contact.db
    "openim_wording": {
        "wording": "文案/提示语（wording）",
        "pinyin": "拼音（pinyin）",
    },

    # message_*.db / biz_message_*.db (WCDB)
    "wcdb_builtin_compression_record": {
        "tablename": "表名（tableName）",
        "columns": "被WCDB压缩的列列表（columns）",
    },

    # general.db
    "revokemessage": {
        "to_user_name": "会话username（撤回消息所在会话）",
        "message_type": "消息类型（local_type）",
        "at_user_list": "@用户列表（字段名推断）",
    },
    "wcfinderlivestatus": {
        "finder_username": "视频号作者username（finder_username）",
        "charge_flag": "是否付费/收费标志（charge_flag）",
    },
    "new_tips": {
        "disable": "禁用标志（disable）",
        "new_tips_content": "提示内容（new_tips_content）",
    },
    "redenvelopetable": {
        "sender_user_name": "红包发送者username",
        "hb_type": "红包类型（hb_type）",
    },
    "wacontact": {
        "external_info": "外部信息（JSON；常见包含 BindWxaInfo/RegisterSource/WxaAppDynamic 等）",
        "contact_pack_data": "联系人打包数据（protobuf-like；常含昵称/品牌名等）",
        "wx_app_opt": "小程序/应用选项（wx_app_opt；位标志/开关；样本为0）",
    },

    # emoticon.db
    "kstoreemoticoncaptionstable": {
        "package_id_": "表情包ID（package_id）",
        "md5_": "表情md5",
        "language_": "语言（language）",
        "caption_": "文案/标题（caption）",
    },
}


KNOWN_TABLE_DESCRIPTIONS: dict[str, str] = {
    # contact.db
    "biz_info": "公众号信息表（公众号类型/菜单/品牌信息等）",
    "chat_room": "群聊基础信息表（群主/成员列表等扩展在 ext_buffer）",
    "chat_room_info_detail": "群聊详细信息表（群公告/群状态等）",
    "chatroom_member": "群聊成员映射表（room_id ↔ member_id）",
    "contact": "联系人核心表（好友/群/公众号等基础信息）",
    "contact_label": "联系人标签表（标签ID与名称）",
    "name2id": "用户名（wxid/群id@chatroom 等）到内部数值ID映射表",
    "encrypt_name2id": "加密用户名到内部数值ID映射表",
    "stranger": "陌生人/临时会话信息表",
    "ticket_info": "票据/会话票据信息表（用途待进一步确认）",
    "stranger_ticket_info": "陌生人票据信息表（用途待进一步确认）",
    "oplog": "操作/同步日志表（增量同步相关）",
    "openim_appid": "OpenIM 应用ID表（企业微信/互通相关）",
    "openim_acct_type": "OpenIM 账号类型表",
    "openim_wording": "OpenIM 文案/提示语表",

    # session.db
    "sessiontable": "会话列表表（会话展示/未读/置顶/隐藏等）",
    "sessiondeletetable": "会话删除记录表",
    "sessionunreadlisttable_1": "未读会话列表表（分表）",
    "sessionunreadstattable_1": "未读统计表（分表）",
    "sessionnocontactinfotable": "会话表（无联系人信息的会话）",
    "session_last_message": "会话最后一条消息缓存/索引表（版本/实现差异）",

    # message_*.db / biz_message_*.db
    "timestamp": "时间戳/增量同步辅助表",
    "deleteinfo": "删除消息记录表（删除/撤回相关）",
    "deleteresinfo": "删除资源记录表（资源删除相关）",
    "sendinfo": "发送相关信息表（发送状态/队列等）",
    "historysysmsginfo": "历史系统消息表",
    "historyaddmsginfo": "历史新增消息表",

    # message_resource.db
    "chatname2id": "会话名 → 会话ID 映射表（资源库维度）",
    "sendername2id": "发送者名 → 发送者ID 映射表（资源库维度）",
    "messageresourceinfo": "消息资源索引表（按消息/会话定位资源）",
    "messageresourcedetail": "消息资源明细表（md5/路径/大小等）",
    "ftsrange": "FTS 范围信息表（搜索/索引辅助）",
    "ftsdeleteinfo": "FTS 删除记录表（索引维护）",

    # media_0.db
    "voiceinfo": "语音数据表（voice_data 等）",

    # hardlink.db
    "db_info": "WCDB Key-Value 元信息表（FTS构建状态/版本/扫描时间等）",
    "dir2id": "目录 → ID 映射表（硬链接索引）",
    "image_hardlink_info_v4": "图片硬链接索引表（v4）",
    "file_hardlink_info_v4": "文件硬链接索引表（v4）",
    "video_hardlink_info_v4": "视频硬链接索引表（v4）",
    "file_checkpoint_v4": "文件索引检查点（增量）",
    "video_checkpoint_v4": "视频索引检查点（增量）",
    "talker_checkpoint_v4": "会话索引检查点（增量）",

    # *_fts.db / message_fts.db
    "table_info": "WCDB Key-Value 元信息表（索引范围/水位/时间戳等）",

    # head_image.db
    "head_image": "头像缓存表（头像 md5/二进制缩略图等）",

    # favorite.db
    "buff": "WCDB Key-Value 缓冲/配置表（收藏等模块的缓存）",
    "fav_db_item": "收藏条目表",
    "fav_tag_db_item": "收藏标签表",
    "fav_bind_tag_db_item": "收藏条目与标签绑定表",

    # emoticon.db
    "kcustomemoticonordertable": "自定义表情排序表（md5 列表）",
    "kexpressrecentuseeemoticontable": "最近使用表情记录（Key-Value）",
    "knonstoreemoticontable": "非商店表情表（用户收藏/外部表情资源；含CDN下载信息）",
    "kstoreemoticonpackagetable": "商店表情包信息表（package 元数据）",
    "kstoreemoticoncaptionstable": "商店表情文案表（多语言 caption）",

    # unspportmsg.db
    "unsupportmessage": "不支持消息表（PC端无法直接展示的消息类型）",

    # bizchat.db
    "chat_group": "BizChat 群组表（企业微信/公众号群组信息）",
    "user_info": "BizChat 用户表（企业微信/公众号用户信息）",
    "my_user_info": "BizChat 当前账号映射表（brand_user_name ↔ user_id）",

    # general.db
    "forwardrecent": "最近转发会话记录表（username/时间）",
    "transfertable": "转账记录表（转账ID/关联消息/状态等）",
    "redenvelopetable": "红包记录表（关联消息/状态等）",
    "ilink_voip": "iLink/群通话相关表（房间ID/成员/状态等）",
    "fmessagetable": "好友验证/陌生人消息表（FMessage）",
    "handoff_remind_v0": "跨设备接力/提醒项表（handoff_remind_v0）",
    "biz_pay_status": "公众号文章付费状态表（url_id/is_paid 等）",
    "biz_subscribe_status": "公众号订阅模板状态表（template_id/is_subscribe）",
    "new_tips": "新提示/新功能提示表",
    "reddot": "小红点提示表",
    "reddot_record": "小红点记录表",
    "wcfinderlivestatus": "视频号直播状态表",
    "teenager_apply_access_agree_info": "青少年模式访问同意记录表",

    # chat_search_index.db（本项目生成）
    "meta": "索引元数据表（schema_version/构建时间等）",
    "message_fts": "全文索引表（fts5，用于搜索）",
}


def simple_heuristic(field_name: str, table_name: str) -> str:
    """简易兜底启发式，避免完全空白"""
    f = field_name.lower()
    t = table_name.lower()
    if f.endswith("id") or f in {"_rowid_", "rowid"} or f == "id":
        return "标识符字段"
    if "time" in f or "timestamp" in f:
        return "时间戳字段"
    if f in {"name", "user_name", "username"}:
        return "用户名/会话名"
    if f in {"content", "message_content", "compress_content"}:
        return "内容/正文字段"
    if "md5" in f:
        return "MD5哈希字段"
    if "status" in f:
        return "状态位/状态码"
    if f.startswith("is_"):
        return "布尔标志字段"
    if f.startswith("wcdb_ct_"):
        return "WCDB压缩控制字段"
    if "buf" in f or "buffer" in f or "blob" in f:
        return "二进制缓冲数据"
    if "url" in f:
        return "URL链接"
    if "size" in f or "count" in f:
        return "数量/大小字段"
    if "seq" in f:
        return "序列号/排序字段"
    # 针对 Msg_* 常见列
    if t.startswith("msg_"):
        if f == "source":
            return "消息来源附加信息（XML/JSON）"
        if f == "local_type":
            return "本地消息类型（local_type）"
    return "未知用途字段"


def compute_field_meaning(analyzer, table_name: str, field_name: str) -> str:
    lt = table_name.lower()
    lf = field_name.lower()

    # 1) 表级覆盖优先
    tmap = KNOWN_FIELD_MEANINGS_BY_TABLE.get(lt)
    if tmap and lf in tmap:
        return tmap[lf]

    # 2) 全局精确映射
    if field_name in KNOWN_FIELD_MEANINGS:
        return KNOWN_FIELD_MEANINGS[field_name]
    if lf in KNOWN_FIELD_MEANINGS:
        return KNOWN_FIELD_MEANINGS[lf]

    # 额外针对 mmreader/zstd 提示
    if lf in {"message_content", "compress_content"}:
        return "消息内容（部分类型为zstd压缩XML：mmreader）"

    # 借用项目内启发式
    if analyzer is not None:
        try:
            return analyzer.get_field_meaning(field_name, table_name)
        except Exception:
            pass

    # 简易兜底
    return simple_heuristic(field_name, table_name)


def guess_table_desc(analyzer, table_name: str) -> str:
    # 简易猜测（优先命中已知表名）
    tl = table_name.lower()

    # 已知表名（大小写不敏感）
    if tl in KNOWN_TABLE_DESCRIPTIONS:
        return KNOWN_TABLE_DESCRIPTIONS[tl]

    # SQLite / WCDB 内置
    if tl == "sqlite_sequence":
        return "SQLite 自增序列表"
    if tl.startswith("wcdb"):
        return "WCDB 内置表（压缩/元数据等）"

    # FTS 内部表（多为 *_data/_idx/_config/_content/_docsize/_aux）
    if "fts" in tl:
        if tl.endswith("_data"):
            return "全文检索（FTS）内部数据表"
        if tl.endswith("_idx"):
            return "全文检索（FTS）内部索引表"
        if tl.endswith("_config"):
            return "全文检索（FTS）内部配置表"
        if tl.endswith("_content"):
            return "全文检索（FTS）内部内容表"
        if tl.endswith("_docsize"):
            return "全文检索（FTS）内部文档长度表"
        if tl.endswith("_aux") or "_aux_" in tl:
            return "全文检索（FTS）辅助表"
        return "全文检索（FTS）表/索引表"

    # 借助分析器的启发式（如果可用，且不是“未知功能表”）
    if analyzer is not None:
        try:
            guessed = analyzer.guess_table_function(table_name)
            if isinstance(guessed, str) and guessed.strip() and guessed.strip() != "未知功能表":
                return guessed.strip()
        except Exception:
            pass

    if tl == "msg" or tl.startswith("msg_"):
        return "某会话的消息表（聊天消息数据）"
    if "name2id" in tl:
        return "用户名到内部ID映射表"
    if "contact" in tl:
        return "联系人/群聊信息表"
    if "session" in tl:
        return "会话信息/未读统计表"
    if "resource" in tl:
        return "消息资源/附件索引表"
    if "voice" in tl:
        return "语音相关数据表"
    if "image" in tl or "img" in tl:
        return "图片相关数据表"
    if "video" in tl:
        return "视频相关数据表"
    if "file" in tl:
        return "文件相关数据表"
    if "sns" in tl:
        return "朋友圈相关数据表"
    return "未知功能表"


def fill_config(template: dict) -> dict:
    # 创建一个分析器实例，仅用于启发式（使用默认配置）
    analyzer = None
    if AnalyzerCls is not None:
        try:
            analyzer = AnalyzerCls(databases_path=str(ROOT / "output" / "databases"),
                                   config_file="nonexistent_config.json")
        except Exception:
            analyzer = None

    # 数据库描述补齐
    db_desc_map = build_db_descriptions()

    def guess_db_desc(db_name: str) -> str:
        # 1) 精确映射优先
        if db_name in db_desc_map:
            return db_desc_map[db_name]

        # 2) 常见分片/变体：message_{n}.db
        m = re.match(r"^message_(\d+)$", db_name)
        if m:
            return f"聊天记录数据库分片（message_{m.group(1)}.db）"

        # 3) 公众号/企业微信消息库：biz_message_{n}.db（结构通常同 message_{n}.db）
        m = re.match(r"^biz_message_(\d+)$", db_name)
        if m:
            return f"公众号消息记录数据库（biz_message_{m.group(1)}.db，结构通常同 message_{m.group(1)}.db）"

        # 4) FTS/索引类库：*_fts.db
        if db_name.endswith("_fts"):
            return "全文索引数据库（FTS）"

        # 5) 退化到 base 前缀
        base = db_name.split("_", 1)[0]
        if base in db_desc_map:
            return db_desc_map[base]

        return "未知用途数据库"

    databases = template.get("databases", {})
    for db_name, db in databases.items():
        if isinstance(db, dict):
            # 数据库级描述
            if not db.get("description"):
                db["description"] = guess_db_desc(db_name)

            # 遍历表
            tables = db.get("tables", {})
            for table_name, table in tables.items():
                if not isinstance(table, dict):
                    continue

                # 表功能描述
                if not table.get("description"):
                    table["description"] = guess_table_desc(analyzer, table_name)

                # 字段含义补齐
                fields = table.get("fields", {})
                if isinstance(fields, dict):
                    for field_name, field_meta in fields.items():
                        if not isinstance(field_meta, dict):
                            continue
                        meaning = field_meta.get("meaning", "")
                        if not meaning:
                            field_meta["meaning"] = compute_field_meaning(analyzer, table_name, field_name)

    # 消息类型映射补充（保留模板 instructional 字段，另外插入真实映射键）
    mt_real = build_message_types_from_ohmywechat()
    message_types = template.get("message_types", {})
    # 合并：新增真实键
    for k, v in mt_real.items():
        message_types[k] = v
    template["message_types"] = message_types

    # 元数据刷新
    meta = template.get("_metadata", {})
    meta["version"] = "1.1"
    meta["generated_time"] = datetime.now().isoformat()
    meta["description"] = "微信数据库字段配置（由模板自动补全，融合启发式与ohmywechat常见类型）"
    template["_metadata"] = meta

    return template


def main():
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

    with TEMPLATE_PATH.open("r", encoding="utf-8") as f:
        template = json.load(f)

    filled = fill_config(template)

    # 写主配置（供分析器默认加载）
    with OUTPUT_MAIN.open("w", encoding="utf-8") as f:
        json.dump(filled, f, ensure_ascii=False, indent=2)

    # 备份写入 output/configs
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_COPY.open("w", encoding="utf-8") as f:
        json.dump(filled, f, ensure_ascii=False, indent=2)

    print("[OK] 生成完成")
    print(f"- 主配置: {OUTPUT_MAIN}")
    print(f"- 备份:   {OUTPUT_COPY}")

    # 简要统计
    dbs = filled.get("databases", {})
    db_count = len(dbs)
    tbl_count = sum(len(d.get("tables", {})) for d in dbs.values() if isinstance(d, dict))
    print(f"- 数据库数: {db_count}, 表数: {tbl_count}")
    print(f"- 消息类型键数: {len(filled.get('message_types', {}))}")


if __name__ == "__main__":
    main()
