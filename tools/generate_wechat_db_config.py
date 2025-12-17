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

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "wechat_db_config_template.json"
OUTPUT_MAIN = ROOT / "wechat_db_config.json"
OUTPUT_DIR = ROOT / "output" / "configs"
OUTPUT_COPY = OUTPUT_DIR / "wechat_db_config.generated.json"

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
        "message_3": "聊天消息分表数据库（示例或分片）",
        "message_fts": "聊天消息全文索引数据库（FTS）",
        "message_resource": "消息资源索引数据库（图片/文件/视频等）",
        "contact": "联系人数据库（好友/群/公众号基础信息）",
        "session": "会话数据库（会话列表与未读统计）",
        "sns": "朋友圈数据库（动态与互动）",
        "favorite": "收藏数据库",
        "emoticon": "表情包数据库",
        "head_image": "头像数据数据库",
        "hardlink": "硬链接索引数据库（资源去重/快速定位）",
        "media_0": "媒体数据数据库（含语音SILK等）",
        "unspportmsg": "不支持消息数据库（客户端不支持的消息类型）",
        "general": "通用/系统数据库（新消息通知/支付等）",
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

    # WCDB 压缩控制
    "WCDB_CT_message_content": "WCDB压缩标记（message_content列）",
    "WCDB_CT_source": "WCDB压缩标记（source列）",
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
    # 优先精确已知映射
    if field_name in KNOWN_FIELD_MEANINGS:
        return KNOWN_FIELD_MEANINGS[field_name]
    lf = field_name.lower()
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
    if analyzer is not None:
        try:
            return analyzer.guess_table_function(table_name)
        except Exception:
            pass
    # 简易猜测
    tl = table_name.lower()
    if tl == "msg" or tl.startswith("msg_"):
        return "某会话的消息表（聊天消息数据）"
    if "name2id" in tl:
        return "用户名到内部ID映射表"
    if "contact" in tl:
        return "联系人/群聊信息表"
    if "session" in tl:
        return "会话信息/未读统计表"
    if "fts" in tl:
        return "全文检索（FTS）内部表"
    if "resource" in tl:
        return "消息资源/附件索引表"
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

    databases = template.get("databases", {})
    for db_name, db in databases.items():
        if isinstance(db, dict):
            # 数据库级描述
            if not db.get("description"):
                # 用已知映射或尝试推断
                db["description"] = db_desc_map.get(db_name, db.get("description", "")) or "未知用途数据库"

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