# Release native builds

Windows and macOS packaging rebuild their WCDB components from the current
`2977094657/WCDB` main revision. Each producer receives a unique build ID and
the current UTC time. The signed components and their manifests expire exactly
45 days after that time. A failed producer stops packaging.

`tools/rebuild_wcdb_release.py` downloads the exact Release asset for each
producer run. The tag is `<component>-<build-id>` and the asset is
`<artifact-name>-<build-id>.zip`; the script requires the Release target to
equal the producer revision, verifies GitHub's asset `digest` against the
downloaded ZIP, and checks the new build window before supplying coordinates to
the existing signature and provenance checks. It does not use Actions artifact
storage or an older Release as a fallback.
The macOS native core, key helper and export-integrity module are built in
parallel. The integrity module uses the exact WeChatDataAnalysis revision being
packaged.

## GitHub configuration

Deploy these production workflows to the main branch of `2977094657/WCDB`:

- `windows-native-production.yml`
- `macos-native-production.yml`
- `macos-key-capture-production.yml`
- `macos-integrity-production.yml`

Configure their protected environments with the existing signing identities:
`windows-native-production`, `macos-native-production` and
`macos-xkey-production`. The workflow `vars` and `secrets` entries specify the
required names. Preserve the existing client, broker, helper and host
certificate pins and the export signing key.

In `LifeArchiveProject/WeChatDataAnalysis`, add repository secret
`WCE_NATIVE_CORE_PRODUCER_TOKEN`. Use a fine-grained token with access only to
`2977094657/WCDB`, Actions read/write and Contents read. Store it directly in
GitHub Actions secrets; do not place it in source files or build arguments.

Keep the trusted signing pins and host signing secrets in
`windows-private-pki-production` and `macos-private-pki-production`.
The macOS environment requires the native client, broker, host and root pins,
their signing identifiers, and the key-helper and host pins used by
`macos-private-build.yml`.

Artifact run IDs, build IDs, source revisions and archive/binary hashes are
generated for each packaging run. They do not need repository-variable updates.
Existing installed packages retain their original expiry; users must install
a release containing the newly built components.
