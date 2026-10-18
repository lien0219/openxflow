import type React from "react";
import { forwardRef } from "react";
import SvgFigranium from "./FigraniumIcon";

export const FigraniumIcon = forwardRef<
  SVGSVGElement,
  React.SVGProps<SVGSVGElement> & { isDark?: boolean }
>((props, ref) => {
  const { isDark, ...svgProps } = props;
  return <SvgFigranium ref={ref} isDark={isDark} {...svgProps} />;
});
