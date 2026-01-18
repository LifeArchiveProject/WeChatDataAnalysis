const fs = require("fs");
const path = require("path");

const pngToIco = require("png-to-ico").default;
const { PNG } = require("pngjs");

const repoRoot = path.resolve(__dirname, "..", "..");
const srcPng = path.join(repoRoot, "frontend", "public", "logo.png");
// Write the generated ICO to the locations electron-builder expects for app+installer icons.
// Also keep a copy in desktop/resources for convenience.
const dstIcos = [
  path.join(repoRoot, "desktop", "resources", "icon.ico"),
  path.join(repoRoot, "desktop", "build", "icon.ico"),
  path.join(repoRoot, "desktop", "build", "installerIcon.ico"),
  path.join(repoRoot, "desktop", "build", "uninstallerIcon.ico"),
  path.join(repoRoot, "desktop", "build", "installerHeaderIcon.ico"),
];

async function main() {
  if (!fs.existsSync(srcPng)) {
    // eslint-disable-next-line no-console
    console.error(`Logo not found: ${srcPng}`);
    process.exit(1);
  }

  const raw = fs.readFileSync(srcPng);
  const input = PNG.sync.read(raw);
  const size = Math.max(input.width, input.height);

  const square = new PNG({ width: size, height: size });
  const dx = Math.floor((size - input.width) / 2);
  const dy = Math.floor((size - input.height) / 2);
  for (let y = 0; y < input.height; y += 1) {
    const srcStart = y * input.width * 4;
    const srcEnd = srcStart + input.width * 4;
    const dstStart = ((y + dy) * size + dx) * 4;
    input.data.copy(square.data, dstStart, srcStart, srcEnd);
  }

  const tmpDir = path.join(repoRoot, "desktop", "build", "icon");
  fs.mkdirSync(tmpDir, { recursive: true });
  const tmpPng = path.join(tmpDir, "logo-square.png");
  fs.writeFileSync(tmpPng, PNG.sync.write(square));

  const buf = await pngToIco(tmpPng);
  for (const dstIco of dstIcos) {
    fs.mkdirSync(path.dirname(dstIco), { recursive: true });
    fs.writeFileSync(dstIco, buf);
  }

  // eslint-disable-next-line no-console
  console.log(`Generated icon(s):\n${dstIcos.map((p) => `- ${p}`).join("\n")}`);
}

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error(err);
  process.exit(1);
});
