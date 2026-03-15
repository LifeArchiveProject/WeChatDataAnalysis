const http = require("http");
const net = require("net");
const path = require("path");
const { spawn, spawnSync } = require("child_process");

const repoRoot = path.resolve(__dirname, "..", "..");
const frontendDir = path.join(repoRoot, "frontend");
const desktopDir = path.join(repoRoot, "desktop");

function parsePort(value) {
  const n = Number.parseInt(String(value || "").trim(), 10);
  return Number.isInteger(n) && n >= 1 && n <= 65535 ? n : null;
}

function log(message) {
  process.stdout.write(`[dev] ${message}\n`);
}

function prefixPipe(stream, prefix) {
  if (!stream) return;
  let pending = "";
  stream.setEncoding("utf8");
  stream.on("data", (chunk) => {
    pending += chunk;
    const lines = pending.split(/\r?\n/);
    pending = lines.pop() || "";
    for (const line of lines) {
      process.stdout.write(`${prefix} ${line}\n`);
    }
  });
  stream.on("end", () => {
    const tail = pending.trim();
    if (tail) process.stdout.write(`${prefix} ${tail}\n`);
  });
}

function isPortAvailable(port, host) {
  return new Promise((resolve) => {
    const server = net.createServer();
    const done = (ok) => {
      try {
        server.close();
      } catch {}
      resolve(ok);
    };
    server.once("error", () => done(false));
    server.once("listening", () => done(true));
    server.listen(port, host);
  });
}

async function choosePort({ label, envName, preferredPort, host, searchLimit = 20 }) {
  if (preferredPort != null) {
    const ok = await isPortAvailable(preferredPort, host);
    if (!ok) throw new Error(`${label}端口 ${preferredPort} 已被占用，请修改环境变量 ${envName}`);
    return preferredPort;
  }

  const startPort = envName === "NUXT_PORT" ? 3000 : 10392;
  for (let port = startPort; port <= startPort + searchLimit; port += 1) {
    if (await isPortAvailable(port, host)) return port;
  }
  throw new Error(`未找到可用的${label}端口（起始 ${startPort}）`);
}

function httpReady(url) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => {
      res.resume();
      resolve(true);
    });
    req.on("error", () => resolve(false));
    req.setTimeout(1000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitForUrl(url, child, timeoutMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (child.exitCode != null) {
      throw new Error(`前端进程提前退出，exitCode=${child.exitCode}`);
    }
    if (await httpReady(url)) return;
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`等待前端启动超时：${url}`);
}

function killChild(child) {
  if (!child || child.killed || child.exitCode != null) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(child.pid), "/t", "/f"], { stdio: "ignore" });
    return;
  }
  try {
    child.kill("SIGTERM");
  } catch {}
}

function spawnLogged(command, args, options, prefix) {
  const child = spawn(command, args, {
    ...options,
    shell: process.platform === "win32",
    stdio: ["inherit", "pipe", "pipe"],
  });
  prefixPipe(child.stdout, `${prefix}`);
  prefixPipe(child.stderr, `${prefix}`);
  return child;
}

async function main() {
  const frontendHost = String(process.env.NUXT_HOST || "127.0.0.1").trim() || "127.0.0.1";
  const requestedFrontendPort = parsePort(process.env.NUXT_PORT);
  const requestedBackendPort = parsePort(process.env.WECHAT_TOOL_PORT);
  const frontendPort = await choosePort({
    label: "前端",
    envName: "NUXT_PORT",
    preferredPort: requestedFrontendPort,
    host: frontendHost,
  });
  const backendPort = await choosePort({
    label: "后端",
    envName: "WECHAT_TOOL_PORT",
    preferredPort: requestedBackendPort,
    host: "127.0.0.1",
  });
  const startUrl = `http://${frontendHost}:${frontendPort}`;

  log(`frontend=${startUrl}`);
  log(`backend=http://127.0.0.1:${backendPort}/api`);

  const sharedEnv = {
    ...process.env,
    NUXT_HOST: frontendHost,
    NUXT_PORT: String(frontendPort),
    WECHAT_TOOL_PORT: String(backendPort),
    ELECTRON_START_URL: startUrl,
  };

  const npmCommand = "npm";
  const electronCommand = "electron";
  const children = new Set();
  let shuttingDown = false;

  const shutdown = (exitCode) => {
    if (shuttingDown) return;
    shuttingDown = true;
    for (const child of children) killChild(child);
    process.exitCode = exitCode;
  };

  process.on("SIGINT", () => shutdown(130));
  process.on("SIGTERM", () => shutdown(143));

  const frontend = spawnLogged(npmCommand, ["run", "dev"], { cwd: frontendDir, env: sharedEnv }, "[frontend]");
  children.add(frontend);
  frontend.once("exit", (code, signal) => {
    log(`frontend exited code=${code} signal=${signal}`);
    shutdown(code == null ? 1 : code);
  });

  await waitForUrl(startUrl, frontend, 60_000);
  log("frontend is ready, starting Electron");

  const electron = spawnLogged(electronCommand, ["."], { cwd: desktopDir, env: sharedEnv }, "[electron]");
  children.add(electron);
  electron.once("exit", (code, signal) => {
    log(`electron exited code=${code} signal=${signal}`);
    shutdown(code == null ? 0 : code);
  });
}

main().catch((err) => {
  process.stderr.write(`[dev] ${err?.stack || err}\n`);
  process.exit(1);
});
