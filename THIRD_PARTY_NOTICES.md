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
| `native/macos/source/image_scan_helper.c` | `resources/key/macos/source/image_scan_helper.c` | `44429e28376c05cd26885668714dc452b8da584bc85422684887033a9f690666` | `77d1d6fef8b0c01df4439f92a258cc8a73af6dc3400b742a9394be90438214f8` | Kept as a local build input; comments and diagnostics were adjusted without changing the helper ABI |
| `native/macos/source/image_scan_entitlements.plist` | `resources/key/macos/source/image_scan_entitlements.plist` | `b9d7e0670d1e50c04ba83c2dcc3d96d39da667e57df0e8d589fa6b701e6173b9` | `995277fd49b775b2daaf812369ae608f14600e1e802a6d86aecbd8bd67d7a741` | Formatting only |
| `native/macos/universal/image_scan_helper` | `resources/key/macos/universal/image_scan_helper` | `d0044463721b393cf4812dce0c711d26a602ecb0a251b7920ef2bb57a8921829` | `7a19a0e95b8bdb638f5e4683d6972bcdfc1b76c8c93a3066cbb6294528edca66` | Rebuilt from the included source as universal2 with deployment target macOS 15.0; ad-hoc signed with the included helper entitlements; source inputs and artifact are locked by `desktop/scripts/macos-image-helper-manifest.json` |
| `native/macos/universal/libwx_key.dylib` | `resources/key/macos/universal/libwx_key.dylib` | `2b734f802c56c913edcd8ae33cff8ee25022acd9b4ab9c4f53d2246fe36f59cd` | `d919fab0bebd53ae742cca25e5289f9353ff6ab04f11121a3559b46b2d9fab3b` | Ad-hoc re-signed so the project copy has a valid standalone signature |

The bundled WeFlow-derived image-scanning resources target macOS 15.0 or earlier, and the desktop package declares macOS 15.0 as its minimum. The image scanning helper and `libwx_key.dylib` are universal binaries.

## Frida Core

The protected macOS database-key helper embeds Frida Core `17.16.4`; it does not require a separately installed Frida or Python runtime. Frida Core is distributed under the wxWindows Library Licence, Version 3.1. The complete upstream license text is included in every helper artifact and packaged application at `native/macos/db-key/THIRD_PARTY_NOTICES/FRIDA-COPYING.txt`. Its digest and file size are pinned by the signed helper manifest and verified again during staging, package verification, and runtime startup.

## ffmpeg-static

Desktop distributions include the platform-specific FFmpeg executable from `ffmpeg-static` so voice messages can be converted to browser-compatible MP3 without a separate system install.

- Package: https://github.com/eugeneware/ffmpeg-static
- Binary builds: https://github.com/ffbinaries/ffbinaries-prebuilt/releases
- Package license: GPL-3.0-or-later
- Distributed license files: `ffmpeg/LICENSE` and `ffmpeg/ffmpeg.LICENSE`
