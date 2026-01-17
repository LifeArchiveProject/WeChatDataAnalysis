const fs = require("fs");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..", "..");
const srcDir = path.join(repoRoot, "frontend", ".output", "public");
const dstDir = path.join(repoRoot, "desktop", "resources", "ui");

if (!fs.existsSync(path.join(srcDir, "index.html"))) {
  // eslint-disable-next-line no-console
  console.error(
    `Nuxt static output not found at ${srcDir}. Run: npm --prefix frontend run generate`
  );
  process.exit(1);
}

fs.mkdirSync(dstDir, { recursive: true });
for (const ent of fs.readdirSync(dstDir, { withFileTypes: true })) {
  if (ent.name === ".gitkeep") continue;
  fs.rmSync(path.join(dstDir, ent.name), { recursive: true, force: true });
}
fs.cpSync(srcDir, dstDir, { recursive: true });

// eslint-disable-next-line no-console
console.log(`Copied UI: ${srcDir} -> ${dstDir}`);
