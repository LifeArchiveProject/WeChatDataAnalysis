# Third-Party Notices

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

## QQ feedback bridge

The optional Windows QQ feedback bridge reuses WeQ's `nt_helper.node` and QQ
flash-transfer protocol implementation. WeQ is copyright H3CoF6 and licensed under
CC BY-NC-SA 4.0: https://github.com/H3CoF6/WeQ
