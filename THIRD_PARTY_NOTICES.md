# Third-Party Notices

## WeFlow macOS native resources

This project includes selected macOS native resources derived from WeFlow:

- Upstream project: https://github.com/hicccc77/WeFlow
- Upstream version used for this import: `5.1.0`
- Upstream license: Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International
- Complete license copy in distributions: `wechat_decrypt_tool/native/macos/WEFLOW_LICENSE.txt`

The application does not load files from a WeFlow checkout at runtime. The files below are copied into this project so source builds, wheels, PyInstaller backends, and desktop packages remain self-contained.

| Distributed file | Upstream file | Upstream SHA-256 | Distributed SHA-256 | Local changes |
| --- | --- | --- | --- | --- |
| `native/macos/universal/image_scan_helper` | `resources/key/macos/universal/image_scan_helper` | `d0044463721b393cf4812dce0c711d26a602ecb0a251b7920ef2bb57a8921829` | `d0044463721b393cf4812dce0c711d26a602ecb0a251b7920ef2bb57a8921829` | None |
| `native/macos/universal/libwx_key.dylib` | `resources/key/macos/universal/libwx_key.dylib` | `2b734f802c56c913edcd8ae33cff8ee25022acd9b4ab9c4f53d2246fe36f59cd` | `2b734f802c56c913edcd8ae33cff8ee25022acd9b4ab9c4f53d2246fe36f59cd` | None |
| `native/macos/arm64/libwcdb_api.dylib` | `resources/wcdb/macos/universal/libwcdb_api.dylib` | `9917b74e6723efea63ac64927c9f6be1ed53133a62ff2c694c68d647690cead1` | `0013c406be9894b6fbf69e7e8de7e273d603826f48e4fde53a30b0d9a7f262e7` | Install ID changed to `@loader_path/libwcdb_api.dylib`; WCDB dependency changed to `@loader_path/../universal/libWCDB.dylib`; ad-hoc re-signed |
| `native/macos/universal/libWCDB.dylib` | `resources/welive/macos/arm64/resources/macos/universal/libWCDB.dylib` | `f751ef9fe3412160584cc872b038fbb85b3b9cb1c6f0a05f99fa9e26bc6e6c34` | `e228a216d532d497ea30ebcd9764c6a37127dd2e87abc505e54b1519103de589` | Install ID changed to `@loader_path/libWCDB.dylib`; ad-hoc re-signed |

The `libwcdb_api.dylib` C API used here is ARM64. Consequently, full WCDB realtime support on macOS is currently limited to Apple Silicon. The image scanning helper and `libWCDB.dylib` are universal binaries.

## ffmpeg-static

Desktop distributions include the platform-specific FFmpeg executable from `ffmpeg-static` so voice messages can be converted to browser-compatible MP3 without a separate system install.

- Package: https://github.com/eugeneware/ffmpeg-static
- Binary builds: https://github.com/ffbinaries/ffbinaries-prebuilt/releases
- Package license: GPL-3.0-or-later
- Distributed license files: `ffmpeg/LICENSE` and `ffmpeg/ffmpeg.LICENSE`
