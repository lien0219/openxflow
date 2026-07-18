import { appendFile, mkdir, rename, stat } from "node:fs/promises";
import path from "node:path";

export interface DesktopLogger {
  info(message: string, context?: Record<string, unknown>): void;
  warn(message: string, context?: Record<string, unknown>): void;
  error(message: string, context?: Record<string, unknown>): void;
}

const SECRET_PATTERN = /(api[_-]?key|authorization|token|secret|password)/i;
const MAX_LOG_SIZE_BYTES = 5 * 1024 * 1024;

export function sanitizeLogValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sanitizeLogValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        SECRET_PATTERN.test(key) ? "[REDACTED]" : sanitizeLogValue(item),
      ]),
    );
  }
  return value;
}

export function createDesktopLogger(logDirectory: string): DesktopLogger {
  const filePath = path.join(logDirectory, "desktop.log");
  const previousFilePath = path.join(logDirectory, "desktop.previous.log");
  let queue = Promise.resolve();

  const write = (
    level: "info" | "warn" | "error",
    message: string,
    context?: Record<string, unknown>,
  ): void => {
    const line = JSON.stringify({
      timestamp: new Date().toISOString(),
      level,
      message,
      context: context ? sanitizeLogValue(context) : undefined,
    });

    queue = queue
      .then(async () => {
        await mkdir(logDirectory, { recursive: true });
        await rotateIfRequired(filePath, previousFilePath);
        await appendFile(filePath, `${line}\n`, "utf8");
      })
      .catch(() => undefined);
  };

  return {
    info: (message, context) => write("info", message, context),
    warn: (message, context) => write("warn", message, context),
    error: (message, context) => write("error", message, context),
  };
}

async function rotateIfRequired(filePath: string, previousFilePath: string): Promise<void> {
  const size = await stat(filePath)
    .then((metadata) => metadata.size)
    .catch(() => 0);
  if (size < MAX_LOG_SIZE_BYTES) return;

  await rename(filePath, previousFilePath).catch(async () => {
    await rename(filePath, `${previousFilePath}.${Date.now()}`).catch(() => undefined);
  });
}
