import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import type { RuntimeStatus } from "../shared/contracts.js";
import { DesktopError, toErrorMessage } from "./errors.js";
import type { DesktopLogger } from "./logger.js";
import { allocateLoopbackPort } from "./port-manager.js";

export interface BackendManagerOptions {
  pythonExecutable: string;
  frontendPath: string;
  environment: NodeJS.ProcessEnv;
  logger: DesktopLogger;
  startupTimeoutMs?: number;
}

export class BackendManager {
  readonly #options: Required<Omit<BackendManagerOptions, "startupTimeoutMs">> & {
    startupTimeoutMs: number;
  };
  #process: ChildProcessWithoutNullStreams | null = null;
  #status: RuntimeStatus = {
    status: "idle",
    port: null,
    pid: null,
    startedAt: null,
    lastError: null,
  };

  constructor(options: BackendManagerOptions) {
    this.#options = {
      ...options,
      startupTimeoutMs: options.startupTimeoutMs ?? 120_000,
    };
  }

  getStatus(): RuntimeStatus {
    return { ...this.#status };
  }

  getUrl(): string {
    if (this.#status.status !== "ready" || this.#status.port === null) {
      throw new DesktopError("RUNTIME_START_FAILED", "OpenXFlow runtime is not ready.");
    }
    return `http://127.0.0.1:${this.#status.port}`;
  }

  async start(): Promise<RuntimeStatus> {
    if (this.#status.status === "ready" || this.#status.status === "starting") {
      return this.getStatus();
    }

    const port = await allocateLoopbackPort();
    const args = [
      "-m",
      "langflow",
      "run",
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
      "--frontend-path",
      path.resolve(this.#options.frontendPath),
      "--no-open-browser",
      "--workers",
      "1",
    ];

    this.#status = {
      status: "starting",
      port,
      pid: null,
      startedAt: new Date().toISOString(),
      lastError: null,
    };
    this.#options.logger.info("Starting OpenXFlow runtime", {
      executable: this.#options.pythonExecutable,
      port,
      frontendPath: this.#options.frontendPath,
    });

    try {
      const child = spawn(this.#options.pythonExecutable, args, {
        env: { ...process.env, ...this.#options.environment },
        cwd: path.dirname(this.#options.frontendPath),
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
      });
      this.#process = child;
      this.#status.pid = child.pid ?? null;

      child.stdout.setEncoding("utf8");
      child.stderr.setEncoding("utf8");
      child.stdout.on("data", (chunk: string) => this.#options.logger.info("runtime.stdout", { chunk }));
      child.stderr.on("data", (chunk: string) => this.#options.logger.warn("runtime.stderr", { chunk }));
      child.once("error", (error) => this.#handleUnexpectedExit(error));
      child.once("exit", (code, signal) => {
        if (this.#status.status !== "stopping" && this.#status.status !== "stopped") {
          this.#handleUnexpectedExit(
            new Error(`Runtime exited unexpectedly (code=${String(code)}, signal=${String(signal)}).`),
          );
        }
      });

      await this.#waitUntilReady(port);
      this.#status.status = "ready";
      this.#options.logger.info("OpenXFlow runtime is ready", { port, pid: this.#status.pid });
      return this.getStatus();
    } catch (error) {
      this.#status.status = "failed";
      this.#status.lastError = toErrorMessage(error);
      await this.stop();
      throw error;
    }
  }

  async restart(): Promise<RuntimeStatus> {
    await this.stop();
    return await this.start();
  }

  async stop(): Promise<void> {
    const child = this.#process;
    if (!child || child.killed) {
      this.#process = null;
      this.#status = { ...this.#status, status: "stopped", pid: null };
      return;
    }

    this.#status.status = "stopping";
    this.#options.logger.info("Stopping OpenXFlow runtime", { pid: child.pid });

    await terminateProcess(child);
    this.#process = null;
    this.#status = { ...this.#status, status: "stopped", pid: null };
  }

  async #waitUntilReady(port: number): Promise<void> {
    const deadline = Date.now() + this.#options.startupTimeoutMs;
    let attempt = 0;

    while (Date.now() < deadline) {
      if (this.#status.status === "failed") {
        throw new DesktopError(
          "RUNTIME_START_FAILED",
          this.#status.lastError ?? "OpenXFlow runtime failed during startup.",
        );
      }
      try {
        const response = await fetch(`http://127.0.0.1:${port}/health`, {
          signal: AbortSignal.timeout(2_000),
        });
        if (response.ok) {
          return;
        }
      } catch {
        // The runtime is still starting. Retry with a bounded backoff.
      }
      attempt += 1;
      await delay(Math.min(250 + attempt * 100, 1_500));
    }

    throw new DesktopError(
      "RUNTIME_TIMEOUT",
      `OpenXFlow did not become ready within ${this.#options.startupTimeoutMs}ms.`,
    );
  }

  #handleUnexpectedExit(error: unknown): void {
    const message = toErrorMessage(error);
    this.#status = { ...this.#status, status: "failed", pid: null, lastError: message };
    this.#options.logger.error("OpenXFlow runtime failed", { message });
  }
}

async function terminateProcess(child: ChildProcessWithoutNullStreams): Promise<void> {
  if (child.pid === undefined) {
    return;
  }

  if (process.platform === "win32") {
    await new Promise<void>((resolve) => {
      const killer = spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
        windowsHide: true,
        stdio: "ignore",
      });
      killer.once("exit", () => resolve());
      killer.once("error", () => resolve());
    });
    return;
  }

  child.kill("SIGTERM");
  const exited = await Promise.race([
    new Promise<boolean>((resolve) => child.once("exit", () => resolve(true))),
    delay(5_000).then(() => false),
  ]);
  if (!exited && !child.killed) {
    child.kill("SIGKILL");
  }
}
