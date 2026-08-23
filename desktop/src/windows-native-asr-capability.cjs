"use strict";

const fs = require("node:fs");
const path = require("node:path");

const WINDOWS_NATIVE_ASR_ABI_VERSION = 1;
const WINDOWS_NATIVE_ASR_FEATURE_BIT = 16;
const WINDOWS_NATIVE_ASR_AUTHORIZATION = "database-read";
const WINDOWS_NATIVE_ASR_DISABLED_AUTHORIZATION = "none";
const WINDOWS_NATIVE_ASR_TARGET = Object.freeze({
  wechatVersion: "4.1.12.26",
  weixinSha256: "4914a621a810ecbc0a132b6ff8f612658cfce323d3989b3e5fe32d4ff343ba46",
});
const WINDOWS_NATIVE_ASR_DISABLED_TARGET = Object.freeze({
  wechatVersion: "",
  weixinSha256: "",
});
const WINDOWS_NATIVE_ASR_EXPORTS = Object.freeze([
  "wce_native_asr_get_status",
  "wce_native_asr_begin",
  "wce_native_asr_poll",
  "wce_native_asr_close",
]);
const MAX_CLIENT_BYTES = 64 * 1024 * 1024;
const MAX_EXPORT_FUNCTIONS = 65_536;
const MAX_EXPORT_NAMES = 65_536;
const MAX_EXPORT_NAME_BYTES = 512;

function peError(message) {
  return new Error(`Invalid Windows native-core client PE: ${message}`);
}

function requireRange(buffer, offset, size, label) {
  if (
    !Number.isSafeInteger(offset) ||
    !Number.isSafeInteger(size) ||
    offset < 0 ||
    size < 0 ||
    offset > buffer.length - size
  ) {
    throw peError(`${label} is outside the file`);
  }
}

function readCString(buffer, offset, label) {
  requireRange(buffer, offset, 1, label);
  const limit = Math.min(buffer.length, offset + MAX_EXPORT_NAME_BYTES + 1);
  const terminator = buffer.indexOf(0, offset);
  if (terminator < 0 || terminator >= limit || terminator === offset) {
    throw peError(`${label} is not a bounded non-empty string`);
  }
  const value = buffer.toString("ascii", offset, terminator);
  if (!/^[\x21-\x7e]+$/.test(value)) {
    throw peError(`${label} contains non-ASCII or control bytes`);
  }
  return value;
}

function readWindowsPeExportNames(clientPath, fsImpl = fs) {
  const resolved = path.resolve(String(clientPath || ""));
  let stat;
  try {
    stat = fsImpl.statSync(resolved);
  } catch {
    throw peError(`cannot read ${path.basename(resolved)}`);
  }
  if (!stat.isFile() || stat.size <= 0 || stat.size > MAX_CLIENT_BYTES) {
    throw peError("file size is invalid");
  }

  const buffer = fsImpl.readFileSync(resolved);
  if (!Buffer.isBuffer(buffer) || buffer.length !== stat.size) {
    throw peError("file read was incomplete");
  }
  requireRange(buffer, 0, 0x40, "DOS header");
  if (buffer.readUInt16LE(0) !== 0x5a4d) throw peError("DOS signature is missing");

  const peOffset = buffer.readUInt32LE(0x3c);
  requireRange(buffer, peOffset, 24, "PE header");
  if (buffer.readUInt32LE(peOffset) !== 0x00004550) {
    throw peError("PE signature is missing");
  }

  const coffOffset = peOffset + 4;
  const sectionCount = buffer.readUInt16LE(coffOffset + 2);
  const optionalSize = buffer.readUInt16LE(coffOffset + 16);
  if (sectionCount <= 0 || sectionCount > 96) throw peError("section count is invalid");

  const optionalOffset = coffOffset + 20;
  requireRange(buffer, optionalOffset, optionalSize, "optional header");
  const magic = buffer.readUInt16LE(optionalOffset);
  let directoryOffset;
  let numberOfDirectoriesOffset;
  if (magic === 0x20b) {
    directoryOffset = optionalOffset + 112;
    numberOfDirectoriesOffset = optionalOffset + 108;
  } else if (magic === 0x10b) {
    directoryOffset = optionalOffset + 96;
    numberOfDirectoriesOffset = optionalOffset + 92;
  } else {
    throw peError("optional-header magic is unsupported");
  }
  requireRange(buffer, numberOfDirectoriesOffset, 4, "data-directory count");
  if (buffer.readUInt32LE(numberOfDirectoriesOffset) < 1) {
    throw peError("export directory is absent");
  }
  requireRange(buffer, directoryOffset, 8, "export data directory");
  const exportRva = buffer.readUInt32LE(directoryOffset);
  const exportSize = buffer.readUInt32LE(directoryOffset + 4);
  if (exportRva === 0 || exportSize < 40) throw peError("export directory is absent");

  const sectionTableOffset = optionalOffset + optionalSize;
  requireRange(buffer, sectionTableOffset, sectionCount * 40, "section table");
  const sections = [];
  for (let index = 0; index < sectionCount; index += 1) {
    const offset = sectionTableOffset + index * 40;
    const virtualSize = buffer.readUInt32LE(offset + 8);
    const virtualAddress = buffer.readUInt32LE(offset + 12);
    const rawSize = buffer.readUInt32LE(offset + 16);
    const rawOffset = buffer.readUInt32LE(offset + 20);
    if (rawSize > 0) {
      requireRange(buffer, rawOffset, rawSize, `section ${index} raw data`);
    }
    sections.push({
      virtualAddress,
      virtualSpan: Math.max(virtualSize, rawSize),
      rawSize,
      rawOffset,
    });
  }

  const rvaToOffset = (rva, size, label) => {
    for (const section of sections) {
      if (rva < section.virtualAddress) continue;
      const delta = rva - section.virtualAddress;
      if (delta > section.virtualSpan || size > section.virtualSpan - delta) continue;
      if (delta > section.rawSize || size > section.rawSize - delta) {
        throw peError(`${label} is not backed by file data`);
      }
      const offset = section.rawOffset + delta;
      requireRange(buffer, offset, size, label);
      return offset;
    }
    throw peError(`${label} RVA is outside mapped sections`);
  };

  const exportOffset = rvaToOffset(exportRva, 40, "export directory");
  const numberOfFunctions = buffer.readUInt32LE(exportOffset + 20);
  const numberOfNames = buffer.readUInt32LE(exportOffset + 24);
  const functionsRva = buffer.readUInt32LE(exportOffset + 28);
  const namesRva = buffer.readUInt32LE(exportOffset + 32);
  const ordinalsRva = buffer.readUInt32LE(exportOffset + 36);
  if (numberOfFunctions > MAX_EXPORT_FUNCTIONS) {
    throw peError("export-function count is too large");
  }
  if (numberOfNames > MAX_EXPORT_NAMES) throw peError("export-name count is too large");
  if (numberOfNames === 0 || namesRva === 0) return new Set();
  if (numberOfFunctions === 0 || functionsRva === 0 || ordinalsRva === 0) {
    throw peError("export tables are incomplete");
  }

  const functionsOffset = rvaToOffset(
    functionsRva,
    numberOfFunctions * 4,
    "export-function table"
  );
  const namesOffset = rvaToOffset(namesRva, numberOfNames * 4, "export-name table");
  const ordinalsOffset = rvaToOffset(
    ordinalsRva,
    numberOfNames * 2,
    "export-ordinal table"
  );
  const names = new Set();
  for (let index = 0; index < numberOfNames; index += 1) {
    const ordinal = buffer.readUInt16LE(ordinalsOffset + index * 2);
    if (ordinal >= numberOfFunctions) {
      throw peError(`export ordinal ${index} is outside the function table`);
    }
    const functionRva = buffer.readUInt32LE(functionsOffset + ordinal * 4);
    if (functionRva === 0) {
      throw peError(`export function ${index} has a null RVA`);
    }
    rvaToOffset(functionRva, 1, `export function ${index}`);
    const nameRva = buffer.readUInt32LE(namesOffset + index * 4);
    const nameOffset = rvaToOffset(nameRva, 1, `export name ${index}`);
    names.add(readCString(buffer, nameOffset, `export name ${index}`));
  }
  return names;
}

function windowsNativeAsrManifestErrors(manifest) {
  const errors = [];
  const fused = manifest?.developmentBuild === false;
  const expectedAbiVersion = fused ? WINDOWS_NATIVE_ASR_ABI_VERSION : 0;
  const expectedFeatureBit = fused ? WINDOWS_NATIVE_ASR_FEATURE_BIT : 0;
  const expectedAuthorization = fused
    ? WINDOWS_NATIVE_ASR_AUTHORIZATION
    : WINDOWS_NATIVE_ASR_DISABLED_AUTHORIZATION;
  const expectedTarget = fused
    ? WINDOWS_NATIVE_ASR_TARGET
    : WINDOWS_NATIVE_ASR_DISABLED_TARGET;
  if (manifest?.nativeAsrAbiVersion !== expectedAbiVersion) {
    errors.push(`nativeAsrAbiVersion must equal ${expectedAbiVersion}`);
  }
  if (manifest?.nativeAsrFeatureBit !== expectedFeatureBit) {
    errors.push(`nativeAsrFeatureBit must equal ${expectedFeatureBit}`);
  }
  if (manifest?.nativeAsrAuthorization !== expectedAuthorization) {
    errors.push(`nativeAsrAuthorization must equal ${expectedAuthorization}`);
  }
  const target = manifest?.nativeAsrTarget;
  if (!target || Array.isArray(target) || typeof target !== "object") {
    errors.push("nativeAsrTarget must be an object");
  } else {
    const targetKeys = Object.keys(target).sort();
    if (
      targetKeys.length !== 2 ||
      targetKeys[0] !== "wechatVersion" ||
      targetKeys[1] !== "weixinSha256"
    ) {
      errors.push("nativeAsrTarget must contain exactly wechatVersion and weixinSha256");
    }
    if (target.wechatVersion !== expectedTarget.wechatVersion) {
      errors.push(
        `nativeAsrTarget.wechatVersion must equal ${expectedTarget.wechatVersion}`
      );
    }
    if (target.weixinSha256 !== expectedTarget.weixinSha256) {
      errors.push(
        `nativeAsrTarget.weixinSha256 must equal ${expectedTarget.weixinSha256}`
      );
    }
  }
  return errors;
}

function assertWindowsNativeAsrCapability({ nativeDir, manifest, fsImpl = fs }) {
  const manifestErrors = windowsNativeAsrManifestErrors(manifest);
  if (manifestErrors.length > 0) {
    throw new Error(`Windows native-core manifest ${manifestErrors.join("; ")}`);
  }
  if (manifest.developmentBuild === true) {
    return Object.freeze({
      available: false,
      abiVersion: 0,
      featureBit: 0,
      authorization: WINDOWS_NATIVE_ASR_DISABLED_AUTHORIZATION,
      target: WINDOWS_NATIVE_ASR_DISABLED_TARGET,
      exports: Object.freeze([]),
    });
  }
  const clientPath = path.join(path.resolve(String(nativeDir || "")), "wechatdb_client.dll");
  const exports = readWindowsPeExportNames(clientPath, fsImpl);
  const missing = WINDOWS_NATIVE_ASR_EXPORTS.filter((name) => !exports.has(name));
  if (missing.length > 0) {
    throw new Error(
      `Windows native-core client is missing fused ASR ABI exports: ${missing.join(", ")}`
    );
  }
  return Object.freeze({
    available: true,
    abiVersion: WINDOWS_NATIVE_ASR_ABI_VERSION,
    featureBit: WINDOWS_NATIVE_ASR_FEATURE_BIT,
    authorization: WINDOWS_NATIVE_ASR_AUTHORIZATION,
    target: WINDOWS_NATIVE_ASR_TARGET,
    exports: WINDOWS_NATIVE_ASR_EXPORTS,
  });
}

module.exports = {
  WINDOWS_NATIVE_ASR_ABI_VERSION,
  WINDOWS_NATIVE_ASR_AUTHORIZATION,
  WINDOWS_NATIVE_ASR_DISABLED_AUTHORIZATION,
  WINDOWS_NATIVE_ASR_DISABLED_TARGET,
  WINDOWS_NATIVE_ASR_FEATURE_BIT,
  WINDOWS_NATIVE_ASR_EXPORTS,
  WINDOWS_NATIVE_ASR_TARGET,
  assertWindowsNativeAsrCapability,
  readWindowsPeExportNames,
  windowsNativeAsrManifestErrors,
};
