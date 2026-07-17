import path from "node:path";
import { app, BrowserWindow, shell } from "electron";
import { BackendManager } from "./backend-manager.js";
import { toErrorMessage } from "./errors.js";
import { registerIpcHandlers } from "./ipc.js";
import { createDesktopLogger } from "./logger.js";
import {
  createBackendEnvironment,
  createDesktopPaths,
  ensureDesktopPaths,
} from "./path-manager.js";
import { resolveRuntimePaths } from "./runtime-resolver.js";
import { disableUntrustedPermissions, installNavigationGuards } from "./security.js";

let mainWindow: BrowserWindow | null = null;
let backendManager: BackendManager | null = null;
let unregisterIpc: (() => void) | null = null;
let shuttingDown = false;

const acquiredLock = app.requestSingleInstanceLock();
if (!acquiredLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.on("before-quit", () => {
    shuttingDown = true;
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length !== 0 || !backendManager) return;
    const status = backendManager.getStatus();
    mainWindow = createMainWindow();
    if (status.status === "ready") {
      void loadApplication(mainWindow, backendManager.getUrl());
    }
  });

  void app
    .whenReady()
    .then(bootstrap)
    .catch((error: unknown) => {
      console.error(error);
      app.quit();
    });
}

async function bootstrap(): Promise<void> {
  app.setName("OpenXFlow");
  const paths = createDesktopPaths(app.getPath("userData"));
  await ensureDesktopPaths(paths);
  const logger = createDesktopLogger(paths.logs);
  const runtime = resolveRuntimePaths({
    isPackaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
    appPath: app.getAppPath(),
  });

  backendManager = new BackendManager({
    pythonExecutable: runtime.pythonExecutable,
    frontendPath: runtime.frontendPath,
    environment: createBackendEnvironment(paths),
    logger,
  });

  process.on("uncaughtException", (error) =>
    logger.error("uncaughtException", { message: error.message }),
  );
  process.on("unhandledRejection", (reason) =>
    logger.error("unhandledRejection", { reason: String(reason) }),
  );

  unregisterIpc = registerIpcHandlers({ app, backendManager, logsDirectory: paths.logs });
  mainWindow = createMainWindow();
  await mainWindow.loadFile(path.join(app.getAppPath(), "dist", "loading", "index.html"));

  try {
    const status = await backendManager.start();
    logger.info("Desktop runtime started", { ...status });
    await loadApplication(mainWindow, backendManager.getUrl());
  } catch (error) {
    const message = toErrorMessage(error);
    logger.error("Desktop bootstrap failed", { message });
    await mainWindow.loadFile(path.join(app.getAppPath(), "dist", "loading", "error.html"), {
      query: { message },
    });
  }

  app.once("before-quit", async (event) => {
    if (!shuttingDown) return;
    event.preventDefault();
    unregisterIpc?.();
    unregisterIpc = null;
    await backendManager?.stop();
    app.exit(0);
  });
}

function createMainWindow(): BrowserWindow {
  const window = new BrowserWindow({
    title: "OpenXFlow",
    width: 1440,
    height: 960,
    minWidth: 1100,
    minHeight: 720,
    show: false,
    backgroundColor: "#111827",
    autoHideMenuBar: process.platform !== "darwin",
    webPreferences: {
      preload: path.join(app.getAppPath(), "dist", "preload", "index.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
    },
  });

  disableUntrustedPermissions(window.webContents);
  window.once("ready-to-show", () => window.show());
  window.on("closed", () => {
    if (mainWindow === window) mainWindow = null;
  });
  return window;
}

async function loadApplication(window: BrowserWindow, applicationUrl: string): Promise<void> {
  installNavigationGuards(window, applicationUrl, async (url) => await shell.openExternal(url));
  await window.loadURL(applicationUrl);
}
