import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestChatMediaRecordVideo(unittest.TestCase):
    def test_fast_probe_finds_chat_history_record_video_under_attach_rec(self):
        from wechat_decrypt_tool.routers.chat_media import _fast_probe_video_path_by_md5

        with TemporaryDirectory() as td:
            wxid_dir = Path(td) / "wxid_test"
            username = "room_for_record_video@chatroom"
            chat_hash = hashlib.md5(username.encode()).hexdigest()
            rec_dir = wxid_dir / "msg" / "attach" / chat_hash / "2026-07" / "Rec" / "record-1"
            video_path = rec_dir / "V" / "0.mp4"
            thumb_path = rec_dir / "Img" / "0_t"
            video_path.parent.mkdir(parents=True, exist_ok=True)
            thumb_path.parent.mkdir(parents=True, exist_ok=True)

            video_payload = b"\x00\x00\x00\x18ftypmp42" + (b"record-video" * 1024)
            video_path.write_bytes(video_payload)
            thumb_path.write_bytes(b"\xff\xd8\xff\xe0" + b"thumb")
            video_md5 = hashlib.md5(video_payload).hexdigest()

            found_video = _fast_probe_video_path_by_md5(
                md5=video_md5,
                wxid_dir=wxid_dir,
                db_storage_dir=None,
                want_thumb=False,
                username=username,
                src_create_time=1783249262,
                file_size=len(video_payload),
            )
            self.assertEqual(found_video, video_path)

            found_thumb = _fast_probe_video_path_by_md5(
                md5=video_md5,
                wxid_dir=wxid_dir,
                db_storage_dir=None,
                want_thumb=True,
                username=username,
                src_create_time=1783249262,
                file_size=len(video_payload),
            )
            self.assertEqual(found_thumb, thumb_path)

    def test_fast_probe_record_video_accepts_index_and_size_when_md5_differs(self):
        from wechat_decrypt_tool.routers.chat_media import _fast_probe_video_path_by_md5

        with TemporaryDirectory() as td:
            wxid_dir = Path(td) / "wxid_test"
            username = "02ebe2dfb0e86941c672c76dfd97291f"
            rec_dir = wxid_dir / "msg" / "attach" / username / "2026-07" / "Rec" / "record-2"
            video_path = rec_dir / "V" / "3.mp4"
            thumb_path = rec_dir / "Img" / "3_t"
            video_path.parent.mkdir(parents=True, exist_ok=True)
            thumb_path.parent.mkdir(parents=True, exist_ok=True)

            video_payload = b"\x00\x00\x00\x18ftypmp42" + (b"fresh-record-video" * 1024)
            video_path.write_bytes(video_payload)
            thumb_path.write_bytes(b"\xff\xd8\xff\xe0" + b"thumb")
            xml_md5_that_does_not_match_file = "2fb258fb6ab7f198f324feadfa569501"
            self.assertNotEqual(hashlib.md5(video_payload).hexdigest(), xml_md5_that_does_not_match_file)

            found_video = _fast_probe_video_path_by_md5(
                md5=xml_md5_that_does_not_match_file,
                wxid_dir=wxid_dir,
                db_storage_dir=None,
                want_thumb=False,
                username=username,
                src_create_time=1783387901,
                file_size=len(video_payload),
                record_index=3,
            )
            self.assertEqual(found_video, video_path)

            found_thumb = _fast_probe_video_path_by_md5(
                md5=xml_md5_that_does_not_match_file,
                wxid_dir=wxid_dir,
                db_storage_dir=None,
                want_thumb=True,
                username=username,
                src_create_time=1783387901,
                file_size=len(video_payload),
                record_index=3,
            )
            self.assertEqual(found_thumb, thumb_path)

    def test_fast_probe_record_video_uses_record_attach_when_username_is_not_attach_dir(self):
        from wechat_decrypt_tool.routers.chat_media import _fast_probe_video_path_by_md5

        with TemporaryDirectory() as td:
            wxid_dir = Path(td) / "wxid_test"
            record_attach = "02ebe2dfb0e86941c672c76dfd97291f"
            selected_contact_username = "wxid_current_selected_contact"
            rec_dir = wxid_dir / "msg" / "attach" / record_attach / "2026-07" / "Rec" / "record-4"
            video_path = rec_dir / "V" / "5.mp4"
            video_path.parent.mkdir(parents=True, exist_ok=True)

            video_payload = b"\x00\x00\x00\x18ftypmp42" + (b"record-attach-video" * 1024)
            video_path.write_bytes(video_payload)

            self.assertIsNone(
                _fast_probe_video_path_by_md5(
                    md5="c7e999b92fcdc2ec176ddbdba9a4e01b",
                    wxid_dir=wxid_dir,
                    db_storage_dir=None,
                    want_thumb=False,
                    username=selected_contact_username,
                    src_create_time=1783389360,
                    file_size=len(video_payload),
                    record_index=5,
                )
            )

            found = _fast_probe_video_path_by_md5(
                md5="c7e999b92fcdc2ec176ddbdba9a4e01b",
                wxid_dir=wxid_dir,
                db_storage_dir=None,
                want_thumb=False,
                username=selected_contact_username,
                src_create_time=1783389360,
                file_size=len(video_payload),
                record_index=5,
                record_attach=record_attach,
            )
            self.assertEqual(found, video_path)

    def test_fast_probe_record_video_accepts_nested_record_index_path(self):
        from wechat_decrypt_tool.routers.chat_media import _fast_probe_video_path_by_md5

        with TemporaryDirectory() as td:
            wxid_dir = Path(td) / "wxid_test"
            record_attach = "02ebe2dfb0e86941c672c76dfd97291f"
            rec_dir = wxid_dir / "msg" / "attach" / record_attach / "2026-07" / "Rec" / "record-6"
            video_path = rec_dir / "V" / "7_1.mp4"
            thumb_path = rec_dir / "Img" / "7_1_t"
            video_path.parent.mkdir(parents=True, exist_ok=True)
            thumb_path.parent.mkdir(parents=True, exist_ok=True)

            video_payload = b"\x00\x00\x00\x18ftypmp42" + (b"nested-record-video" * 1024)
            video_path.write_bytes(video_payload)
            thumb_path.write_bytes(b"\xff\xd8\xff\xe0" + b"thumb")
            xml_md5_that_does_not_match_file = "c2227767284deec7e01d97e1b591a4fd"
            self.assertNotEqual(hashlib.md5(video_payload).hexdigest(), xml_md5_that_does_not_match_file)

            self.assertIsNone(
                _fast_probe_video_path_by_md5(
                    md5=xml_md5_that_does_not_match_file,
                    wxid_dir=wxid_dir,
                    db_storage_dir=None,
                    want_thumb=False,
                    username="selected_contact",
                    src_create_time=1783305224,
                    file_size=len(video_payload),
                    record_index=1,
                    record_attach=record_attach,
                )
            )

            found_video = _fast_probe_video_path_by_md5(
                md5=xml_md5_that_does_not_match_file,
                wxid_dir=wxid_dir,
                db_storage_dir=None,
                want_thumb=False,
                username="selected_contact",
                src_create_time=1783305224,
                file_size=len(video_payload),
                record_index=1,
                record_index_path="7_1",
                record_attach=record_attach,
            )
            self.assertEqual(found_video, video_path)

            found_thumb = _fast_probe_video_path_by_md5(
                md5=xml_md5_that_does_not_match_file,
                wxid_dir=wxid_dir,
                db_storage_dir=None,
                want_thumb=True,
                username="selected_contact",
                src_create_time=1783305224,
                file_size=len(video_payload),
                record_index=1,
                record_index_path="7_1",
                record_attach=record_attach,
            )
            self.assertEqual(found_thumb, thumb_path)

            self.assertIsNone(
                _fast_probe_video_path_by_md5(
                    md5=xml_md5_that_does_not_match_file,
                    wxid_dir=wxid_dir,
                    db_storage_dir=None,
                    want_thumb=False,
                    username="selected_contact",
                    src_create_time=1783305224,
                    file_size=len(video_payload),
                    record_index=1,
                    record_index_path="../7_1",
                    record_attach=record_attach,
                )
            )

    def test_fast_probe_record_video_accepts_nested_index_path_when_xml_size_differs(self):
        from wechat_decrypt_tool.routers.chat_media import _fast_probe_video_path_by_md5

        with TemporaryDirectory() as td:
            wxid_dir = Path(td) / "wxid_test"
            record_attach = "02ebe2dfb0e86941c672c76dfd97291f"
            rec_dir = wxid_dir / "msg" / "attach" / record_attach / "2026-07" / "Rec" / "record-8"
            video_path = rec_dir / "V" / "0_1.mp4"
            thumb_path = rec_dir / "Img" / "0_1_t"
            video_path.parent.mkdir(parents=True, exist_ok=True)
            thumb_path.parent.mkdir(parents=True, exist_ok=True)

            video_payload = b"\x00\x00\x00\x18ftypmp42" + (b"nested-record-video-size-diff" * 1024)
            video_path.write_bytes(video_payload)
            thumb_path.write_bytes(b"\xff\xd8\xff\xe0" + b"thumb")
            xml_md5_that_does_not_match_file = "2373892b509fa12b391c09ececf3a00d"
            xml_datasize_that_differs = max(1, len(video_payload) - 4096)

            found_video = _fast_probe_video_path_by_md5(
                md5=xml_md5_that_does_not_match_file,
                wxid_dir=wxid_dir,
                db_storage_dir=None,
                want_thumb=False,
                username="selected_contact",
                src_create_time=1783308779,
                file_size=xml_datasize_that_differs,
                record_index=1,
                record_index_path="0_1",
                record_attach=record_attach,
            )
            self.assertEqual(found_video, video_path)

            found_thumb = _fast_probe_video_path_by_md5(
                md5=xml_md5_that_does_not_match_file,
                wxid_dir=wxid_dir,
                db_storage_dir=None,
                want_thumb=True,
                username="selected_contact",
                src_create_time=1783308779,
                file_size=xml_datasize_that_differs,
                record_index=1,
                record_index_path="0_1",
                record_attach=record_attach,
            )
            self.assertEqual(found_thumb, thumb_path)

    def test_fast_probe_record_image_accepts_rec_index_with_prefixed_payload(self):
        from wechat_decrypt_tool.routers.chat_media import _fast_probe_record_image_in_chat_attach

        with TemporaryDirectory() as td:
            wxid_dir = Path(td) / "wxid_test"
            username = "room_for_record_image@chatroom"
            chat_hash = hashlib.md5(username.encode()).hexdigest()
            img_dir = wxid_dir / "msg" / "attach" / chat_hash / "2026-07" / "Rec" / "record-3" / "Img"
            image_path = img_dir / "1"
            img_dir.mkdir(parents=True, exist_ok=True)

            image_payload = b"\xff\xd8\xff\xe0" + (b"record-image" * 1024)
            image_path.write_bytes(b"\x07\x08\x56\x32" + (b"\x00" * 27) + image_payload)

            found = _fast_probe_record_image_in_chat_attach(
                wxid_dir_str=str(wxid_dir),
                username=username,
                md5="c72982b5bf0460934337c7b23e45c1c8",
                src_create_time=1783387899,
                file_size=len(image_payload),
                record_index=1,
            )
            self.assertEqual(found, str(image_path))

    def test_fast_probe_record_image_accepts_nested_record_index_path(self):
        from wechat_decrypt_tool.routers.chat_media import _fast_probe_record_image_in_chat_attach

        with TemporaryDirectory() as td:
            wxid_dir = Path(td) / "wxid_test"
            record_attach = "02ebe2dfb0e86941c672c76dfd97291f"
            img_dir = wxid_dir / "msg" / "attach" / record_attach / "2026-07" / "Rec" / "record-7" / "Img"
            image_path = img_dir / "12_3"
            img_dir.mkdir(parents=True, exist_ok=True)

            image_payload = b"\xff\xd8\xff\xe0" + (b"nested-record-image" * 1024)
            image_path.write_bytes(b"\x07\x08\x56\x32" + (b"\x00" * 27) + image_payload)

            self.assertIsNone(
                _fast_probe_record_image_in_chat_attach(
                    wxid_dir_str=str(wxid_dir),
                    username="selected_contact",
                    md5="9ea7f6d7a31b7a2367330421bee0b06d",
                    src_create_time=1783310164,
                    file_size=len(image_payload),
                    record_index=3,
                    record_attach=record_attach,
                )
            )

            found = _fast_probe_record_image_in_chat_attach(
                wxid_dir_str=str(wxid_dir),
                username="selected_contact",
                md5="9ea7f6d7a31b7a2367330421bee0b06d",
                src_create_time=1783310164,
                file_size=len(image_payload),
                record_index=3,
                record_index_path="12_3",
                record_attach=record_attach,
            )
            self.assertEqual(found, str(image_path))

            self.assertIsNone(
                _fast_probe_record_image_in_chat_attach(
                    wxid_dir_str=str(wxid_dir),
                    username="selected_contact",
                    md5="9ea7f6d7a31b7a2367330421bee0b06d",
                    src_create_time=1783310164,
                    file_size=len(image_payload),
                    record_index=3,
                    record_index_path="12/3",
                    record_attach=record_attach,
                )
            )

    def test_fast_probe_record_image_uses_record_attach_when_username_is_not_attach_dir(self):
        from wechat_decrypt_tool.routers.chat_media import _fast_probe_record_image_in_chat_attach

        with TemporaryDirectory() as td:
            wxid_dir = Path(td) / "wxid_test"
            record_attach = "02ebe2dfb0e86941c672c76dfd97291f"
            selected_contact_username = "wxid_current_selected_contact"
            img_dir = wxid_dir / "msg" / "attach" / record_attach / "2026-07" / "Rec" / "record-5" / "Img"
            image_path = img_dir / "0"
            img_dir.mkdir(parents=True, exist_ok=True)

            image_payload = b"\xff\xd8\xff\xe0" + (b"record-image" * 1024)
            image_path.write_bytes(b"\x07\x08\x56\x32" + (b"\x00" * 27) + image_payload)

            self.assertIsNone(
                _fast_probe_record_image_in_chat_attach(
                    wxid_dir_str=str(wxid_dir),
                    username=selected_contact_username,
                    md5="caaada8d2f3574d6fc7951f0c92474ba",
                    src_create_time=1783388820,
                    file_size=len(image_payload),
                    record_index=0,
                )
            )

            found = _fast_probe_record_image_in_chat_attach(
                wxid_dir_str=str(wxid_dir),
                username=selected_contact_username,
                md5="caaada8d2f3574d6fc7951f0c92474ba",
                src_create_time=1783388820,
                file_size=len(image_payload),
                record_index=0,
                record_attach=record_attach,
            )
            self.assertEqual(found, str(image_path))


if __name__ == "__main__":
    unittest.main()
