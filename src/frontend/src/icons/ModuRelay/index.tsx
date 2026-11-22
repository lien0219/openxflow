import React, { forwardRef } from "react";
import modurelayMark from "./modurelay-mark.png";

export const ModuRelayIcon = forwardRef<
  SVGSVGElement,
  React.SVGProps<SVGSVGElement>
>((props, ref) => (
  <svg
    ref={ref}
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 512 512"
    width="1em"
    height="1em"
    {...props}
  >
    <image href={modurelayMark} width="512" height="512" />
  </svg>
));
