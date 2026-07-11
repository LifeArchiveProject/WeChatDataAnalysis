import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestExportFormatLayoutFrontend(unittest.TestCase):
    def test_chat_export_uses_four_columns(self):
        source = (ROOT / "frontend" / "components" / "chat" / "ChatExportDialog.vue").read_text(encoding="utf-8")
        self.assertIn("grid-template-columns: repeat(4, minmax(0, 1fr));", source)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", source)

    def test_record_export_uses_four_columns(self):
        source = (ROOT / "frontend" / "components" / "RecordExportDialog.vue").read_text(encoding="utf-8")
        self.assertIn("grid-template-columns: repeat(4, minmax(0, 1fr));", source)
        self.assertIn("height: auto;", source)

    def test_contacts_show_only_four_target_formats(self):
        source = (ROOT / "frontend" / "pages" / "contacts.vue").read_text(encoding="utf-8")
        self.assertIn('class="grid grid-cols-2 gap-2 sm:grid-cols-4"', source)
        self.assertNotIn('type="radio" value="csv"', source)
        for value in ("html", "json", "txt", "excel"):
            self.assertIn(f'type="radio" value="{value}"', source)

    def test_contacts_browser_html_export_uses_profile_cards(self):
        source = (ROOT / "frontend" / "pages" / "contacts.vue").read_text(encoding="utf-8")
        self.assertIn('class="contact-card"', source)
        self.assertIn('class="contact-avatar"', source)
        self.assertIn("item?.avatarLink || item?.avatar", source)
        self.assertNotIn('const headers = columns.map(([, label]) => `<th>', source)
        html_fields = source.split("const contactHtmlIdentityFields", 1)[1].split("const renderContactHtmlCard", 1)[0]
        for label in ("用户名", "显示名称", "备注", "昵称", "微信号", "地区", "来源"):
            self.assertIn(f"'{label}'", source)
        for label in ("类型", "公众号类型", "公众号类型码", "国家/地区码", "省份", "城市", "来源场景码"):
            self.assertNotIn(f"'{label}'", html_fields)
        self.assertNotIn("<figcaption>", source)
        self.assertIn("grid-template-columns:repeat(4,minmax(0,1fr))", source)
        self.assertIn("width:50px;height:50px", source)

    def test_sns_format_grid_is_stable(self):
        source = (ROOT / "frontend" / "pages" / "sns.vue").read_text(encoding="utf-8")
        self.assertIn('class="grid grid-cols-2 gap-2 sm:grid-cols-4"', source)
        self.assertIn("min-w-[280px]", source)

    def test_readme_export_table_matches_supported_formats(self):
        source = (ROOT / "README.md").read_text(encoding="utf-8")
        table = source.split("## 可导出的内容", 1)[1].split("## 加入群聊", 1)[0]
        for content in ("聊天记录", "朋友圈", "联系人", "收藏", "好友验证", "小程序", "视频号直播", "转账与红包", "服务号记录"):
            row = next(line for line in table.splitlines() if line.startswith(f"| {content} |"))
            self.assertIn("HTML / JSON / TXT / Excel", row, content)
        self.assertIn("Excel 格式生成 `.xlsx`", table)


if __name__ == "__main__":
    unittest.main()
