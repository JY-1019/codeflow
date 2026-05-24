const { app, BrowserWindow, net, protocol, shell } = require("electron");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");
const { pathToFileURL } = require("node:url");

const API_HOST = "127.0.0.1";
const API_PORT = 8019;
const API_HEALTH_URL = `http://${API_HOST}:${API_PORT}/api/health`;
const APP_PROTOCOL = "codeflow-light";
const APP_HOST = "app";

protocol.registerSchemesAsPrivileged([
  {
    scheme: APP_PROTOCOL,
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
    },
  },
]);

let backendProcess = null;
let isQuitting = false;
let appProtocolRegistered = false;
const windowsBySession = new Map();

const launchContext = () => {
  const sessionId = process.env.CODEFLOW_LIGHT_SESSION_ID || "";
  return {
    projectRoot: process.env.CODEFLOW_LIGHT_PROJECT_ROOT || process.env.PWD || repoRoot(),
    sessionId,
    sessionTitle: process.env.CODEFLOW_LIGHT_SESSION_TITLE || codexThreadName(sessionId),
  };
};

const gotLock = app.requestSingleInstanceLock(launchContext());
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", (_event, _commandLine, _workingDirectory, additionalData) => {
    if (isQuitting) return;
    openLaunchContext(additionalData);
  });
}

function repoRoot() {
  return path.resolve(__dirname, "..", "..");
}

function backendDir() {
  if (app.isPackaged) return path.join(process.resourcesPath, "backend");
  return path.join(repoRoot(), "backend");
}

function backendExecutableName() {
  return process.platform === "win32" ? "codeflow-light-backend.exe" : "codeflow-light-backend";
}

function packagedBackendExecutable() {
  const configured = process.env.CODEFLOW_LIGHT_BACKEND_EXECUTABLE;
  if (configured && fs.existsSync(configured)) return configured;

  const candidates = [
    app.isPackaged ? path.join(process.resourcesPath, "backend-bin", backendExecutableName()) : "",
    path.join(repoRoot(), "frontend", "backend-bin", backendExecutableName()),
    path.join(repoRoot(), "backend-bin", backendExecutableName()),
  ].filter(Boolean);

  return candidates.find((candidate) => fs.existsSync(candidate)) || "";
}

function userDataPath(...parts) {
  return path.join(app.getPath("userData"), ...parts);
}

function healthCheck(timeoutMs = 900) {
  return new Promise((resolve) => {
    const req = http.get(API_HEALTH_URL, { timeout: timeoutMs }, (res) => {
      res.resume();
      resolve(res.statusCode && res.statusCode >= 200 && res.statusCode < 300);
    });
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
    req.on("error", () => resolve(false));
  });
}

async function waitForBackend(timeoutMs = 12_000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (await healthCheck()) return true;
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  return false;
}

function pythonFromVenv(venvDir) {
  return process.platform === "win32"
    ? path.join(venvDir, "Scripts", "python.exe")
    : path.join(venvDir, "bin", "python");
}

function ensureBackendPython() {
  if (process.env.CODEFLOW_PYTHON) return process.env.CODEFLOW_PYTHON;

  const devPython = pythonFromVenv(path.join(backendDir(), "venv"));
  if (fs.existsSync(devPython)) return devPython;

  const venvDir = userDataPath("backend-venv");
  const venvPython = pythonFromVenv(venvDir);
  if (!fs.existsSync(venvPython)) {
    const created = createBackendVenv(venvDir);
    if (!created) return systemPythonFallback();
  }

  const marker = path.join(venvDir, ".codeflow-light-installed");
  if (!fs.existsSync(marker)) {
    spawnSync(venvPython, ["-m", "pip", "install", "--upgrade", "pip"], { stdio: "ignore" });
    const installed = spawnSync(venvPython, ["-m", "pip", "install", backendDir()], {
      stdio: "ignore",
    });
    if (installed.status === 0) {
      fs.writeFileSync(marker, new Date().toISOString(), "utf8");
    }
  }
  return venvPython;
}

function createBackendVenv(venvDir) {
  for (const candidate of systemPythonCandidates()) {
    const created = spawnSync(candidate.command, [...candidate.args, "-m", "venv", venvDir], {
      stdio: "ignore",
    });
    if (created.status === 0) return true;
  }
  return false;
}

function systemPythonCandidates() {
  if (process.platform === "win32") {
    return [
      { command: "py", args: ["-3"] },
      { command: "python", args: [] },
      { command: "python3", args: [] },
    ];
  }
  return [
    { command: "python3", args: [] },
    { command: "python", args: [] },
  ];
}

function systemPythonFallback() {
  return process.platform === "win32" ? "python" : "python3";
}

function normalizeLaunchContext(raw) {
  const fallback = launchContext();
  if (!raw || typeof raw !== "object") return fallback;
  const sessionId = typeof raw.sessionId === "string" ? raw.sessionId : fallback.sessionId;
  return {
    projectRoot:
      typeof raw.projectRoot === "string" && raw.projectRoot.trim()
        ? raw.projectRoot
        : fallback.projectRoot,
    sessionId,
    sessionTitle:
      typeof raw.sessionTitle === "string" && raw.sessionTitle.trim()
        ? raw.sessionTitle
        : codexThreadName(sessionId) || fallback.sessionTitle,
  };
}

function windowKey(context) {
  return context.sessionId || `project:${context.projectRoot || "default"}`;
}

function focusWindow(win) {
  try {
    if (win.isDestroyed()) return false;
    if (win.isMinimized()) win.restore();
    if (win.isDestroyed()) return false;
    win.focus();
    return true;
  } catch (error) {
    logLaunchError(error);
    return false;
  }
}

function openLaunchContext(rawContext) {
  try {
    const context = normalizeLaunchContext(rawContext);
    const open = () => {
      void createOrFocusWindow(context).catch(logLaunchError);
    };
    if (app.isReady()) {
      open();
      return;
    }
    void app.whenReady().then(open).catch(logLaunchError);
  } catch (error) {
    logLaunchError(error);
  }
}

async function ensureBackend(projectRoot) {
  if (await healthCheck()) return true;

  const logPath = userDataPath("backend.log");
  const logFd = fs.openSync(logPath, "a");
  const env = {
    ...process.env,
    HOST: API_HOST,
    PORT: String(API_PORT),
    CODEFLOW_LIGHT_PROJECT_ROOT: projectRoot || process.env.PWD || repoRoot(),
  };

  const backendExecutable = packagedBackendExecutable();
  if (app.isPackaged && !backendExecutable) {
    throw new Error(
      "Packaged Codeflow Light is missing its bundled backend executable. " +
        "Rebuild the app with npm run build:backend before packaging."
    );
  }
  const backendCommand = backendExecutable || ensureBackendPython();
  const backendArgs = backendExecutable ? [] : ["main.py"];
  const backendCwd = backendExecutable ? path.dirname(backendExecutable) : backendDir();

  backendProcess = spawn(backendCommand, backendArgs, {
    cwd: backendCwd,
    env,
    detached: false,
    stdio: ["ignore", logFd, logFd],
  });
  backendProcess.on("exit", () => {
    backendProcess = null;
  });

  return waitForBackend();
}

async function createOrFocusWindow(rawContext) {
  if (isQuitting) return null;
  const context = normalizeLaunchContext(rawContext);
  const key = windowKey(context);
  const existing = windowsBySession.get(key);
  if (existing && focusWindow(existing)) {
    return existing;
  }
  if (existing) windowsBySession.delete(key);

  await ensureBackend(context.projectRoot);
  if (isQuitting) return null;
  return createWindow(context);
}

function createWindow(context) {
  const sessionLabel = context.sessionTitle || shortSessionLabel(context.sessionId);
  const titleSuffix = sessionLabel ? ` - ${formatTitleLabel(sessionLabel, 64)}` : "";
  const win = new BrowserWindow({
    width: 1440,
    height: 940,
    minWidth: 1100,
    minHeight: 720,
    backgroundColor: "#020617",
    title: `Codeflow Light${titleSuffix}`,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  windowsBySession.set(windowKey(context), win);
  win.on("closed", () => {
    windowsBySession.delete(windowKey(context));
  });

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  if (process.env.VITE_DEV_SERVER_URL) {
    win.loadURL(urlWithContext(process.env.VITE_DEV_SERVER_URL, context));
  } else {
    win.loadURL(urlWithContext(`${APP_PROTOCOL}://${APP_HOST}/index.html`, context));
  }
  return win;
}

function registerAppProtocol() {
  if (appProtocolRegistered) return;
  protocol.handle(APP_PROTOCOL, (request) => {
    const filePath = distFilePath(request.url);
    return net.fetch(pathToFileURL(filePath).toString());
  });
  appProtocolRegistered = true;
}

function distFilePath(rawUrl) {
  const distDir = path.resolve(__dirname, "..", "dist");
  const url = new URL(rawUrl);
  const relativePath = decodeURIComponent(url.pathname).replace(/^\/+/, "") || "index.html";
  const requestedPath = path.resolve(distDir, relativePath);
  const isInsideDist = requestedPath === distDir || requestedPath.startsWith(`${distDir}${path.sep}`);
  if (!isInsideDist || !fs.existsSync(requestedPath)) {
    return path.join(distDir, "index.html");
  }
  return requestedPath;
}

function urlWithContext(rawUrl, context) {
  const url = new URL(rawUrl);
  const query = queryForContext(context);
  for (const [key, value] of Object.entries(query)) {
    url.searchParams.set(key, value);
  }
  return url.toString();
}

function queryForContext(context) {
  const query = {};
  if (context.projectRoot) query.project_root = context.projectRoot;
  if (context.sessionId) query.session_id = context.sessionId;
  if (context.sessionTitle) query.session_title = formatTitleLabel(context.sessionTitle, 80);
  return query;
}

function shortSessionLabel(sessionId) {
  if (!sessionId) return "";
  return sessionId.length > 12 ? sessionId.slice(0, 8) : sessionId;
}

function formatTitleLabel(value, maxLength) {
  const compact = String(value || "").replace(/\s+/g, " ").trim();
  if (compact.length <= maxLength) return compact;
  return `${compact.slice(0, Math.max(0, maxLength - 1))}…`;
}

function codexThreadName(sessionId) {
  if (!sessionId) return "";
  const indexPath = path.join(codexHome(), "session_index.jsonl");
  if (!fs.existsSync(indexPath)) return "";

  try {
    const lines = fs.readFileSync(indexPath, "utf8").split(/\r?\n/);
    for (let index = lines.length - 1; index >= 0; index -= 1) {
      const line = lines[index].trim();
      if (!line) continue;
      let item;
      try {
        item = JSON.parse(line);
      } catch {
        continue;
      }
      if (item && item.id === sessionId && typeof item.thread_name === "string") {
        return item.thread_name.trim();
      }
    }
  } catch {
    return "";
  }
  return "";
}

function codexHome() {
  const configured = process.env.CODEX_HOME || "";
  const trimmed = configured.trim();
  if (!trimmed) return path.join(os.homedir(), ".codex");
  if (trimmed === "~") return os.homedir();
  if (trimmed.startsWith("~/")) return path.join(os.homedir(), trimmed.slice(2));
  return path.resolve(trimmed);
}

function logLaunchError(error) {
  console.error("[codeflow-light] failed to open/focus window", error);
}

app.whenReady().then(async () => {
  registerAppProtocol();
  await createOrFocusWindow(launchContext());

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      void createOrFocusWindow(launchContext());
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  isQuitting = true;
  windowsBySession.clear();
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});
