import { appendFile, mkdir } from "node:fs/promises";
import path from "node:path";

export interface DesktopLogger {
  info(message: string, context?: Record<string, unknown>): void;
  warn(message: string, context?: Record<string, unknown>): void;
  error(message: string, context?: Record<string, unknown>): void;
}

const SECRET_PATTERN = /(api[_-]?key|authorization|token|secret|password)/i;

function sanitize(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(sanitize);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, SECRET_PATTERN.test(key) ? "[REDACTED]" : sanitize(item)]),
    );
  }
  return value;
}

export function createDesktopLogger(logDirectory: string): DesktopLogger {
  const filePath = path.join(logDirectory, "desktop.log");
  void mkdir(logDirectory, { recursive: true });

  const write = (level: "info" | "warn" | "error", message: string, context?: Record<string, unknown>) => {
    const line = JSON.stringify({
      timestamp: new Date().toISOString(),
      level,
      message,
      context: context ? sanitize(context) : undefined,
    });
    void appendFile(filePath, `${line}\n`, "utf8").catch(() => undefined);
  };

  return {
    info: (message, context) => write("info", message, context),
    warn: (message, context) => write("warn", message, context),
    error: (message, context) => write("error", message, context),
  };
}
