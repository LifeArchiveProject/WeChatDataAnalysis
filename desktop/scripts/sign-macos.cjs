"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { signAsync } = require("@electron/osx-sign");

module.exports = async function signMacos(options) {
  const helperSuffix = path.join(
    "Contents",
    "Resources",
    "backend",
    "native",
    "macos",
    "universal",
    "image_scan_helper"
  );
  const helperPath = path.join(options.app, helperSuffix);
  const helperEntitlements = path.resolve(
    __dirname,
    "..",
    "..",
    "src",
    "wechat_decrypt_tool",
    "native",
    "macos",
    "source",
    "image_scan_entitlements.plist"
  );
  if (!fs.existsSync(helperPath)) throw new Error(`Packaged image helper not found: ${helperPath}`);
  if (!fs.existsSync(helperEntitlements)) throw new Error(`Image helper entitlements not found: ${helperEntitlements}`);

  const baseOptionsForFile = options.optionsForFile;
  await signAsync({
    ...options,
    optionsForFile(filePath) {
      const inherited = typeof baseOptionsForFile === "function" ? baseOptionsForFile(filePath) || {} : {};
      if (filePath === helperPath || filePath.endsWith(path.sep + helperSuffix)) {
        return { ...inherited, entitlements: helperEntitlements };
      }
      return inherited;
    },
  });
};
