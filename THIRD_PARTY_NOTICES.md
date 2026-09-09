# Third-Party Notices

## AI provider icons

AI provider SVG brand marks in `frontend/assets/icons/ai-providers/` come from
[`@lobehub/icons-static-svg` 1.95.0](https://www.npmjs.com/package/@lobehub/icons-static-svg/v/1.95.0),
part of [Lobe Icons](https://github.com/lobehub/lobe-icons), copyright (c) 2023 LobeHub.
The SVG files are distributed unchanged under the MIT License. Color variants
retain their original colors; monochrome variants use themed CSS masks. The license is included in
`docs/licenses/lobe-icons-MIT.txt`. Brand marks identify their respective services.

The PNG app icons are original assets served by the respective official websites:

- Doubao: https://lf-flow-web-cdn.doubao.com/obj/flow-doubao/favicon/new-doubao/128x128.png
- LM Studio: https://lmstudio.ai/assets/marketing/logo-192x192.png

These PNG assets are not covered by the Lobe Icons MIT License. All brand names
and trademarks belong to their respective owners and are used to identify services.

## Optional local voice transcription

The optional local voice transcription feature uses the following Python packages:

| Package | Upstream project | License |
| --- | --- | --- |
| `faster-whisper` | https://github.com/SYSTRAN/faster-whisper | MIT |
| `CTranslate2` | https://github.com/OpenNMT/CTranslate2 | MIT |
| `PyAV` | https://github.com/PyAV-Org/PyAV | BSD-3-Clause |
| `OpenCC Python Reimplemented` | https://github.com/yichen0831/opencc-python | Apache-2.0 |
| `ONNX Runtime` | https://github.com/microsoft/onnxruntime | MIT |
| `Hugging Face tokenizers` | https://github.com/huggingface/tokenizers | Apache-2.0 |

Whisper model weights are not included in this repository or its pull request. Users provide or download model weights separately and must follow the selected model's license and usage terms.

## Optional macOS WCDB passphrase capture

The optional Apple Silicon LLDB capture workflow adapts the breakpoint and
register-inspection approach from
[`TANGandXUE/wcdb-key-tool`](https://github.com/TANGandXUE/wcdb-key-tool),
which is distributed under the MIT License. The integration adds target
database validation, transaction recovery, signature verification, and
privacy-preserving diagnostics; it does not bundle user databases or keys.
The complete upstream license text is included at
`docs/licenses/wcdb-key-tool-MIT.txt`.

## Optional local semantic search

Local retrieval uses ONNX Runtime (MIT), Hugging Face Hub (Apache-2.0),
Hugging Face tokenizers (Apache-2.0), and sqlite-vec (MIT / Apache-2.0 dual license).
Embedding weights are downloaded separately from fixed Hugging Face revisions:
BAAI BGE Small/Base Chinese converted to ONNX by Xenova, and intfloat
multilingual E5 Small. Their selected repositories declare MIT; source,
revision and file hashes are recorded in `local_search_models.json`.

The optional NVIDIA component downloads pinned official Python wheels for CUDA
Runtime, cuBLAS, cuDNN and cuFFT. These libraries retain their NVIDIA license
terms and bundled notices; they are not relicensed under this repository's
license. ONNX Runtime GPU remains MIT. See `docs/local-semantic-search.md` and
`local_search_gpu.json` for the exact component list and validation status.
