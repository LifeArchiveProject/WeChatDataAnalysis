"use strict";

const fs = require("node:fs");
const crypto = require("node:crypto");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const DEPLOYMENT_TARGET = "15.0";
const repoRoot = path.resolve(__dirname, "..", "..");
const sourceRoot = path.join(
  repoRoot,
  "src",
  "wechat_decrypt_tool",
  "native",
  "macos",
  "source"
);
const sourcePath = path.join(sourceRoot, "image_scan_helper.c");
const entitlementsPath = path.join(sourceRoot, "image_scan_entitlements.plist");
const outputPath = path.join(sourceRoot, "..", "universal", "image_scan_helper");
const buildDir = path.join(repoRoot, "desktop", "build", "macos-native");
const temporaryDir = path.join(buildDir, `image-scan-helper-${process.pid}`);
const temporaryOutput = path.join(temporaryDir, "image_scan_helper");
const manifestPath = path.join(repoRoot, "desktop", "scripts", "macos-image-helper-manifest.json");

function sha256(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function repoPath(filePath) {
  return path.relative(repoRoot, filePath).split(path.sep).join("/");
}

function writeManifest() {
  const manifest = {
    schemaVersion: 1,
    deploymentTarget: DEPLOYMENT_TARGET,
    architectures: ["arm64", "x86_64"],
    inputs: [sourcePath, entitlementsPath].map((filePath) => ({
      path: repoPath(filePath),
      sha256: sha256(filePath),
    })),
    artifact: {
      path: repoPath(outputPath),
      sha256: sha256(outputPath),
    },
  };
  fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: repoRoot,
    encoding: "utf8",
    stdio: options.capture ? "pipe" : "inherit",
    env: {
      ...process.env,
      MACOSX_DEPLOYMENT_TARGET: DEPLOYMENT_TARGET,
    },
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    const details = [result.stdout, result.stderr].filter(Boolean).join("\n").trim();
    throw new Error(
      `${command} ${args.join(" ")} failed (${result.status})${details ? `:\n${details}` : ""}`
    );
  }
  return String(result.stdout || "").trim();
}

function main() {
  if (process.platform !== "darwin") {
    throw new Error("The macOS image helper must be built on macOS with Xcode Command Line Tools.");
  }
  for (const required of [sourcePath, entitlementsPath]) {
    if (!fs.existsSync(required)) throw new Error(`Missing helper build input: ${required}`);
  }

  fs.mkdirSync(buildDir, { recursive: true });
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.rmSync(temporaryDir, { recursive: true, force: true });
  fs.mkdirSync(temporaryDir, { recursive: true });

  try {
    run("xcrun", [
      "clang",
      "-std=c11",
      "-O2",
      "-arch",
      "arm64",
      "-arch",
      "x86_64",
      `-mmacosx-version-min=${DEPLOYMENT_TARGET}`,
      sourcePath,
      "-o",
      temporaryOutput,
      "-ldl",
    ]);
    run("codesign", [
      "--force",
      "--sign",
      "-",
      "--entitlements",
      entitlementsPath,
      temporaryOutput,
    ]);

    const architectures = run("lipo", ["-archs", temporaryOutput], { capture: true }).split(/\s+/);
    for (const architecture of ["arm64", "x86_64"]) {
      if (!architectures.includes(architecture)) {
        throw new Error(`Rebuilt image helper is missing ${architecture}: ${architectures.join(" ")}`);
      }
    }

    fs.copyFileSync(temporaryOutput, outputPath);
    fs.chmodSync(outputPath, 0o755);
    writeManifest();
    process.stdout.write(
      `Built universal image helper for macOS ${DEPLOYMENT_TARGET}+: ${outputPath}\n`
    );
  } finally {
    fs.rmSync(temporaryDir, { recursive: true, force: true });
  }
}

try {
  main();
} catch (error) {
  process.stderr.write(`${error?.stack || error}\n`);
  process.exitCode = 1;
}
