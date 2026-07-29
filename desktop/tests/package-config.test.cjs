const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");
const { detachMountedDmg } = require("../scripts/macos-package-verifier.cjs");

const desktopRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(desktopRoot, "..");
const packageJson = JSON.parse(fs.readFileSync(path.join(desktopRoot, "package.json"), "utf8"));

test("desktop package includes and unpacks the Koffi native runtime", () => {
  const nodeModulesRule = packageJson.build.files.find(
    (item) => item && typeof item === "object" && item.from === "node_modules"
  );
  assert.ok(nodeModulesRule);
  assert.ok(nodeModulesRule.filter.includes("koffi/**/*"));
  assert.ok(packageJson.build.asarUnpack.includes("node_modules/koffi/**/*"));
});

test("desktop package ships the platform ffmpeg binary and license", () => {
  const resource = packageJson.build.extraResources.find(
    (item) => item && item.from === "node_modules/ffmpeg-static"
  );
  assert.ok(resource);
  assert.equal(resource.to, "ffmpeg");
  assert.ok(resource.filter.includes("ffmpeg"));
  assert.ok(resource.filter.includes("ffmpeg.exe"));
  assert.ok(resource.filter.includes("LICENSE"));
});

test("macOS package resources required by realtime WCDB and image scanning exist", () => {
  const nativeRoot = path.join(repoRoot, "src", "wechat_decrypt_tool", "native", "macos");
  const required = [
    path.join(nativeRoot, "arm64", "libwcdb_api.dylib"),
    path.join(nativeRoot, "universal", "libWCDB.dylib"),
    path.join(nativeRoot, "universal", "libwx_key.dylib"),
    path.join(nativeRoot, "universal", "image_scan_helper"),
    path.join(nativeRoot, "source", "image_scan_helper.c"),
    path.join(nativeRoot, "source", "image_scan_entitlements.plist"),
    path.join(desktopRoot, "src", "wcdb-sidecar.cjs"),
  ];
  for (const resource of required) assert.ok(fs.existsSync(resource), resource);
  fs.accessSync(path.join(nativeRoot, "universal", "image_scan_helper"), fs.constants.X_OK);
});

test("macOS release config emits architecture-specific DMG and ZIP assets", () => {
  assert.deepEqual(packageJson.build.mac.target, ["dmg", "zip"]);
  assert.match(packageJson.build.mac.artifactName, /mac-\$\{arch\}/);
  assert.equal(packageJson.build.mac.hardenedRuntime, true);
  assert.equal(packageJson.build.mac.minimumSystemVersion, "15.0");
  assert.equal(packageJson.scripts["dist:mac"], "npm run dist:mac:arm64");
  assert.match(packageJson.scripts["dist:mac:arm64"], /verify:mac:native/);
  assert.match(packageJson.scripts["dist:mac:arm64"], /--arm64/);
  assert.doesNotMatch(packageJson.scripts["dist:mac:arm64"], /--x64|--universal/);
  assert.equal(packageJson.build.afterPack, "scripts/after-pack.cjs");
  assert.equal(packageJson.build.afterSign, "scripts/after-sign.cjs");
  assert.equal(packageJson.build.mac.sign, "scripts/sign-macos.cjs");
  assert.match(packageJson.scripts["dist:mac:arm64:release"], /MACOS_DISTRIBUTION_BUILD=1/);
  assert.match(packageJson.scripts["dist:mac:arm64:release"], /forceCodeSigning=true/);
});

test("macOS release exposes a reusable packaged smoke test", () => {
  const smokeScript = path.join(desktopRoot, "scripts", "smoke-macos-package.cjs");
  assert.equal(packageJson.scripts["smoke:mac"], "node scripts/smoke-macos-package.cjs");
  assert.equal(
    packageJson.scripts["verify:mac:distribution"],
    "node scripts/verify-macos-distribution.cjs"
  );
  assert.ok(fs.existsSync(smokeScript), smokeScript);
});

test("macOS native resources expose reproducible build and architecture verification", () => {
  const buildScript = fs.readFileSync(
    path.join(desktopRoot, "scripts", "build-macos-image-helper.cjs"),
    "utf8"
  );
  const verifyScript = fs.readFileSync(
    path.join(desktopRoot, "scripts", "verify-macos-native.cjs"),
    "utf8"
  );

  assert.equal(
    packageJson.scripts["build:mac:image-helper"],
    "node scripts/build-macos-image-helper.cjs"
  );
  assert.equal(
    packageJson.scripts["verify:mac:native"],
    "node scripts/verify-macos-native.cjs --arch arm64 --require-host-arch"
  );
  assert.match(buildScript, /MACOSX_DEPLOYMENT_TARGET/);
  assert.match(buildScript, /-mmacosx-version-min=/);
  assert.match(buildScript, /"arm64"/);
  assert.match(buildScript, /"x86_64"/);
  assert.match(verifyScript, /only arm64 is complete/);
  assert.match(verifyScript, /maximumNativeMinOS/);
  assert.match(verifyScript, /@loader_path\/\.\.\/universal\/libWCDB\.dylib/);
  assert.match(verifyScript, /ffmpeg-static/);
  assert.match(verifyScript, /darwin_arm64/);
  assert.match(verifyScript, /run\("nm", \["-gU", filePath\]\)/);
  for (const symbol of [
    "InitProtection",
    "wcdb_init",
    "wcdb_open_account",
    "wcdb_close_account",
    "wcdb_set_my_wxid",
    "wcdb_get_sessions",
    "wcdb_get_messages",
    "wcdb_open_message_cursor",
    "wcdb_fetch_message_batch",
    "wcdb_get_contacts_compact",
    "wcdb_get_sns_timeline",
    "wcdb_list_media_dbs",
    "wcdb_scan_media_stream",
    "wcdb_exec_query",
    "wcdb_free_string",
  ]) {
    assert.match(verifyScript, new RegExp(`"${symbol}"`));
  }
});

test("macOS image helper manifest locks source inputs and the tracked artifact", () => {
  const manifest = JSON.parse(
    fs.readFileSync(path.join(desktopRoot, "scripts", "macos-image-helper-manifest.json"), "utf8")
  );
  const digest = (filePath) => crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");

  assert.equal(manifest.schemaVersion, 1);
  assert.equal(manifest.deploymentTarget, "15.0");
  assert.deepEqual(manifest.architectures, ["arm64", "x86_64"]);
  for (const entry of [...manifest.inputs, manifest.artifact]) {
    const filePath = path.join(repoRoot, entry.path);
    assert.ok(fs.existsSync(filePath), filePath);
    assert.equal(digest(filePath), entry.sha256, entry.path);
  }
});

test("macOS helper package probe uses a nonexistent PID and a hard timeout", () => {
  const smokeScript = fs.readFileSync(
    path.join(desktopRoot, "scripts", "smoke-macos-package.cjs"),
    "utf8"
  );

  assert.match(smokeScript, /\["2147483647", "0"\.repeat\(32\)\]/);
  assert.match(smokeScript, /timeout:\s*5_000/);
  assert.match(smokeScript, /assert\.ifError\(imageHelperProbe\.error\)/);
});

test("macOS package smoke performs a real image-key memory scan", () => {
  const smokeScript = fs.readFileSync(
    path.join(desktopRoot, "scripts", "smoke-macos-package.cjs"),
    "utf8"
  );

  assert.match(smokeScript, /image_key_candidate\[33\]/);
  assert.match(smokeScript, /createCipheriv\("aes-128-ecb"/);
  assert.match(smokeScript, /spawnSync\(imageHelper/);
  assert.match(smokeScript, /Buffer\.from\(helperPayload\.aesKey, "hex"\)/);
  assert.match(smokeScript, /await probePackagedImageScanner\(imageHelper, tempRoot\)/);
});

test("unsigned macOS CI packages are ad-hoc sealed before DMG creation", () => {
  const afterPack = fs.readFileSync(path.join(desktopRoot, "scripts", "after-pack.cjs"), "utf8");

  assert.match(afterPack, /electronPlatformName !== "darwin"/);
  assert.match(afterPack, /"--deep"/);
  assert.match(afterPack, /"--options",\s*\n\s*"runtime"/);
  assert.match(afterPack, /codesign.*--verify/s);
  assert.match(afterPack, /MACOS_DISTRIBUTION_BUILD/);
});

test("macOS signing keeps debugger entitlement on the image helper only", () => {
  const appEntitlements = fs.readFileSync(path.join(desktopRoot, "entitlements.mac.plist"), "utf8");
  const helperEntitlements = fs.readFileSync(
    path.join(repoRoot, "src", "wechat_decrypt_tool", "native", "macos", "source", "image_scan_entitlements.plist"),
    "utf8"
  );
  const signer = fs.readFileSync(path.join(desktopRoot, "scripts", "sign-macos.cjs"), "utf8");
  const afterSign = fs.readFileSync(path.join(desktopRoot, "scripts", "after-sign.cjs"), "utf8");

  assert.doesNotMatch(appEntitlements, /com\.apple\.security\.get-task-allow/);
  assert.doesNotMatch(appEntitlements, /com\.apple\.security\.cs\.debugger/);
  assert.match(helperEntitlements, /com\.apple\.security\.cs\.debugger/);
  assert.match(signer, /image_scan_helper/);
  assert.match(signer, /helperEntitlements/);
  assert.match(afterSign, /stapler.*staple/s);
  assert.match(afterSign, /Developer ID Application/);
});

test("macOS archive verification checks ZIP, mounted DMG, signing, and distribution policy", () => {
  const verifier = fs.readFileSync(path.join(desktopRoot, "scripts", "macos-package-verifier.cjs"), "utf8");
  const smoke = fs.readFileSync(path.join(desktopRoot, "scripts", "smoke-macos-package.cjs"), "utf8");

  assert.match(verifier, /ditto/);
  assert.match(verifier, /hdiutil/);
  assert.match(verifier, /codesign/);
  assert.match(verifier, /Developer ID Application/);
  assert.match(verifier, /syspolicy_check/);
  assert.match(verifier, /stapler/);
  assert.match(verifier, /withMacosArtifacts/);
  assert.match(smoke, /withMacosArtifacts\(\{ distribution: false \}, async \(\{ zipAppPath \}\)/);
  assert.match(smoke, /runPackagedRuntimeSmoke\(zipAppPath\)/);
  assert.doesNotMatch(smoke, /findPackagedApp/);
});

test("macOS DMG cleanup retries a busy mount with force detach", () => {
  const calls = [];
  detachMountedDmg("/tmp/wda-mounted-dmg", (command, args) => {
    calls.push([command, args]);
    if (!args.includes("-force")) throw new Error("normal detach: resource busy");
  });

  assert.deepEqual(calls, [
    ["hdiutil", ["detach", "/tmp/wda-mounted-dmg"]],
    ["hdiutil", ["detach", "-force", "/tmp/wda-mounted-dmg"]],
  ]);
});

test("macOS DMG cleanup preserves both detach failures", () => {
  assert.throws(
    () => detachMountedDmg("/tmp/wda-mounted-dmg", (command, args) => {
      const mode = args.includes("-force") ? "forced" : "normal";
      throw new Error(`${command} ${mode} detach output`);
    }),
    (error) => {
      assert.ok(error instanceof AggregateError);
      assert.equal(error.errors.length, 2);
      assert.match(error.message, /hdiutil normal detach output/);
      assert.match(error.message, /hdiutil forced detach output/);
      assert.match(error.message, /mount directory was preserved/);
      return true;
    }
  );
});

test("release workflow builds, smoke-tests, and uploads macOS artifacts", () => {
  const workflow = fs.readFileSync(path.join(repoRoot, ".github", "workflows", "release.yml"), "utf8");
  const macJob = workflow.match(/\n  build-macos-arm64:\n([\s\S]*?)(?=\n  publish-release:\n)/)?.[1] || "";

  assert.match(macJob, /runs-on:\s*macos-15/);
  assert.match(macJob, /test -n "\$version"/);
  assert.match(macJob, /run:\s*npm run dist:mac:arm64:release/);
  assert.match(macJob, /run:\s*npm run verify:mac:native/);
  assert.match(macJob, /run:\s*npm run smoke:mac/);
  assert.match(macJob, /run:\s*npm run verify:mac:distribution/);
  assert.match(macJob, /secrets\.MACOS_CSC_LINK/);
  assert.match(macJob, /secrets\.MACOS_APPLE_APP_SPECIFIC_PASSWORD/);
  assert.match(macJob, /secrets\.MACOS_APPLE_TEAM_ID/);
  assert.doesNotMatch(macJob, /CSC_IDENTITY_AUTO_DISCOVERY/);
  assert.match(macJob, /uses:\s*actions\/upload-artifact@v4/);
  assert.match(macJob, /desktop\/dist\/\*\.dmg/);
  assert.match(macJob, /desktop\/dist\/\*\.zip/);
});

test("macOS and Windows packages are built only by the tag-triggered release workflow", () => {
  const workflowsDir = path.join(repoRoot, ".github", "workflows");
  const workflow = fs.readFileSync(path.join(workflowsDir, "release.yml"), "utf8");

  // Desktop packaging is expensive (macos-15 runners bill at 10x); keep it off
  // pull requests and main pushes so both platforms build on the same trigger.
  assert.match(workflow, /^on:\n  push:\n    tags:\n      - "v\*"\n/m);
  assert.match(workflow, /\n  build-windows:\n/);
  assert.match(workflow, /\n  build-macos-arm64:\n/);

  for (const entry of fs.readdirSync(workflowsDir)) {
    const source = fs.readFileSync(path.join(workflowsDir, entry), "utf8");
    if (!/npm run (dist|smoke):/.test(source)) continue;
    assert.equal(
      entry,
      "release.yml",
      `${entry} packages the desktop app outside the tag-triggered release workflow`
    );
  }
});

test("macOS native window controls reserve the sidebar title-bar area", () => {
  const preload = fs.readFileSync(path.join(desktopRoot, "src", "preload.cjs"), "utf8");
  const main = fs.readFileSync(path.join(desktopRoot, "src", "main.cjs"), "utf8");
  const sidebar = fs.readFileSync(path.join(repoRoot, "frontend", "components", "SidebarRail.vue"), "utf8");

  assert.match(preload, /platform:\s*process\.platform/);
  assert.match(main, /titleBarStyle:\s*"hiddenInset"/);
  assert.match(main, /trafficLightPosition/);
  assert.match(sidebar, /isMacosDesktop/);
  assert.match(sidebar, /macos-sidebar-titlebar-spacer/);
  assert.match(sidebar, /--desktop-titlebar-height/);
});

test("frontend joins copied output paths using the native path style", async () => {
  const modulePath = path.join(repoRoot, "frontend", "lib", "native-path.js");
  const { joinNativePath } = await import(pathToFileURL(modulePath).href);

  assert.equal(joinNativePath("/Users/demo/output/", "wxid_demo"), "/Users/demo/output/wxid_demo");
  assert.equal(joinNativePath("D:\\wechat\\output\\", "wxid_demo"), "D:\\wechat\\output\\wxid_demo");
  assert.equal(joinNativePath("\\\\server\\share\\output", "wxid_demo"), "\\\\server\\share\\output\\wxid_demo");
});
