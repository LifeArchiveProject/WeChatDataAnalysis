const fs = require("fs");
const path = require("path");

function parseDesktopSettingsText(rawText) {
  const text = String(rawText ?? "").replace(/^\uFEFF/, "");
  const parsed = JSON.parse(text || "{}");
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
  return parsed;
}

function writeDesktopSettingsFileAtomic(filePath, settings) {
  const targetPath = path.resolve(String(filePath || ""));
  const parentDir = path.dirname(targetPath);
  const tempPath = path.join(
    parentDir,
    `.${path.basename(targetPath)}.tmp-${process.pid}-${Date.now()}-${Math.random().toString(16).slice(2)}`
  );
  const contents = JSON.stringify(settings, null, 2);
  let fd = null;

  fs.mkdirSync(parentDir, { recursive: true });
  try {
    fd = fs.openSync(tempPath, "wx");
    fs.writeFileSync(fd, contents, { encoding: "utf8" });
    fs.fsyncSync(fd);
    fs.closeSync(fd);
    fd = null;
    fs.renameSync(tempPath, targetPath);
  } catch (err) {
    if (fd != null) {
      try {
        fs.closeSync(fd);
      } catch {}
    }
    try {
      fs.rmSync(tempPath, { force: true });
    } catch {}
    throw err;
  }
}

module.exports = {
  parseDesktopSettingsText,
  writeDesktopSettingsFileAtomic,
};
