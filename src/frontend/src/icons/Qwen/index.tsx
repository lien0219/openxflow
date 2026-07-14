import type React from "react";
import { forwardRef } from "react";

export const QwenIcon = forwardRef<
  SVGSVGElement,
  React.PropsWithChildren<Record<string, never>>
>((props, ref) => (
  <svg
    ref={ref}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    {...props}
  >
    <path
      d="M12 3a9 9 0 1 0 7.4 14.13L22 21l-3.87-2.13A9 9 0 0 0 12 3Z"
      fill="currentColor"
    />
    <path
      d="M9 8.5h5.1a2.9 2.9 0 1 1-2.05 4.95L15 16.4h-2.2l-2.33-2.38H9V8.5Zm2 1.8v1.92h3.1a.96.96 0 1 0 0-1.92H11Z"
      fill="var(--background, white)"
    />
  </svg>
));
