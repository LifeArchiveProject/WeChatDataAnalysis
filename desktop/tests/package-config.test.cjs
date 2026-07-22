const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");

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
    path.join(desktopRoot, "src", "wcdb-sidecar.cjs"),
  ];
  for (const resource of required) assert.ok(fs.existsSync(resource), resource);
  fs.accessSync(path.join(nativeRoot, "universal", "image_scan_helper"), fs.constants.X_OK);
});

test("macOS release config emits architecture-specific DMG and ZIP assets", () => {
  assert.deepEqual(packageJson.build.mac.target, ["dmg", "zip"]);
  assert.match(packageJson.build.mac.artifactName, /mac-\$\{arch\}/);
  assert.equal(packageJson.build.mac.hardenedRuntime, true);
});

test("macOS release exposes a reusable packaged smoke test", () => {
  const smokeScript = path.join(desktopRoot, "scripts", "smoke-macos-package.cjs");
  assert.equal(packageJson.scripts["smoke:mac"], "node scripts/smoke-macos-package.cjs");
  assert.ok(fs.existsSync(smokeScript), smokeScript);
});

test("release workflow builds, smoke-tests, and uploads macOS artifacts", () => {
  const workflow = fs.readFileSync(path.join(repoRoot, ".github", "workflows", "release.yml"), "utf8");
  const macJob = workflow.match(/\n  build-macos-arm64:\n([\s\S]*?)(?=\n  publish-release:\n)/)?.[1] || "";

  assert.match(macJob, /runs-on:\s*macos-15/);
  assert.match(macJob, /run:\s*npm run dist:mac/);
  assert.match(macJob, /run:\s*npm run smoke:mac/);
  assert.match(macJob, /uses:\s*actions\/upload-artifact@v4/);
  assert.match(macJob, /desktop\/dist\/\*\.dmg/);
  assert.match(macJob, /desktop\/dist\/\*\.zip/);
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
