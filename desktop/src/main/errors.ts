export type DesktopErrorCode =
  | "RUNTIME_NOT_FOUND"
  | "RUNTIME_START_FAILED"
  | "RUNTIME_TIMEOUT"
  | "PORT_ALLOCATION_FAILED"
  | "PERMISSION_DENIED"
  | "IPC_VALIDATION_FAILED";

export class DesktopError extends Error {
  readonly code: DesktopErrorCode;
  readonly causeValue: unknown;

  constructor(code: DesktopErrorCode, message: string, causeValue?: unknown) {
    super(message);
    this.name = "DesktopError";
    this.code = code;
    this.causeValue = causeValue;
  }
}

export function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}
