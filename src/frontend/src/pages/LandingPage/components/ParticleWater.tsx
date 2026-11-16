import { useEffect, useRef } from "react";
import { cn } from "@/utils/utils";
import { useLandingMotion } from "../hooks/use-landing-motion";
import "./particle-water.css";

type Ripple = { x: number; y: number; started: number };
type WaterPoint = {
  x: number;
  y: number;
  radius: number;
  amplitude: number;
  swellSin: number;
  swellCos: number;
  driftSin: number;
  driftCos: number;
};
type AmbientPoint = {
  x: number;
  y: number;
  radius: number;
  wave: number;
  drift: number;
  rise: number;
};

const SHADES = 8;

export default function ParticleWater({
  variant = "hero",
}: {
  variant?: "hero" | "ambient" | "pipeline";
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const elapsed = useRef(0);
  const { paused } = useLandingMotion();

  useEffect(() => {
    const canvas = ref.current;
    const hero = canvas?.parentElement;
    if (!canvas || !hero) return;

    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let context: CanvasRenderingContext2D | null = null;
    let visible = false;
    let width = 0;
    let height = 0;
    let pixelRatio = 1;
    let frame = 0;
    let lastFrame = 0;
    let lastTick = 0;
    let lastRipple = 0;
    let color = getComputedStyle(canvas).color;
    let ripples: Ripple[] = [];
    let waterPoints: WaterPoint[][] = [];
    let ambientPoints: AmbientPoint[][] = [];
    const frameInterval =
      1000 / (variant === "ambient" ? 15 : variant === "pipeline" ? 24 : 30);

    // Cache geometry, opacity bands, and wave phases until the canvas changes size.
    const buildPoints = () => {
      waterPoints = Array.from({ length: SHADES }, () => []);
      ambientPoints = Array.from({ length: SHADES }, () => []);
      if (variant === "ambient") {
        const count = width < 600 ? 36 : 64;
        for (const side of [-1, 1]) {
          for (let strand = 0; strand < 6; strand++) {
            for (let point = 0; point < count; point++) {
              const v = point / (count - 1);
              const alpha = (0.18 + Math.sin(v * Math.PI) * 0.27) * 0.85;
              ambientPoints[Math.floor((alpha / 0.6) * SHADES)].push({
                x: width * (side < 0 ? 0.07 : 0.93) + (strand - 2.5) * 7,
                y: height * (v * 1.16 - 0.08),
                radius: strand % 3 === 0 ? 1.1 : 0.65,
                wave: v * 5 + strand * 0.07,
                drift: v * 9,
                rise: v * 6 + strand * 0.3,
              });
            }
          }
        }
        return;
      }

      const columns = Math.min(88, Math.max(28, Math.round(width / 18)));
      const rows = variant === "pipeline" ? 12 : width < 600 ? 16 : 24;
      for (let row = 0; row < rows; row++) {
        const depth = row / (rows - 1);
        const perspective = depth ** 1.35;
        const spread = 0.68 + perspective * 0.46;
        for (let column = 0; column < columns; column++) {
          const u = (column + (row % 2) * 0.35) / (columns - 0.65);
          const alpha =
            Math.sin(u * Math.PI) ** 0.65 *
            Math.sin(depth * Math.PI) ** 0.7 *
            (1 -
              0.6 * Math.exp(-(((u - 0.5) / 0.24) ** 2)) * (1 - depth) ** 2) *
            (0.19 + depth * 0.34);
          if (alpha < 0.015) continue;
          waterPoints[Math.floor((alpha / 0.6) * SHADES)].push({
            x: width * (0.5 + (u - 0.5) * spread),
            y:
              height *
              (variant === "pipeline"
                ? 0.12 + perspective * 0.83
                : 0.49 + perspective * 0.52),
            radius: 0.55 + perspective * 0.85,
            amplitude: height * (0.018 + depth * 0.045),
            swellSin: Math.sin(u * 9 + depth * 4),
            swellCos: Math.cos(u * 9 + depth * 4),
            driftSin: Math.sin(u * 5 - depth * 3),
            driftCos: Math.cos(u * 5 - depth * 3),
          });
        }
      }
    };

    const draw = (time: number) => {
      if (!width || !height) return;
      context ??= canvas.getContext("2d");
      if (!context) return;
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      context.clearRect(0, 0, width, height);
      context.fillStyle = color;
      if (variant === "ambient") {
        for (const [shade, points] of ambientPoints.entries()) {
          if (!points.length) continue;
          context.globalAlpha = ((shade + 0.5) / SHADES) * 0.6;
          context.beginPath();
          for (const point of points) {
            const x =
              point.x +
              Math.sin(point.wave + time * 0.12) * width * 0.08 +
              Math.cos(point.drift - time * 0.16) * width * 0.025;
            const y = point.y + Math.sin(point.rise + time * 0.16) * 18;
            context.moveTo(x + point.radius, y);
            context.arc(x, y, point.radius, 0, Math.PI * 2);
          }
          context.fill();
        }
        return;
      }

      ripples = ripples.filter((ripple) => time - ripple.started < 3.5);
      const swellSin = Math.sin(time * 0.65);
      const swellCos = Math.cos(time * 0.65);
      const driftSin = Math.sin(time * 0.4);
      const driftCos = Math.cos(time * 0.4);

      // One fill per opacity band instead of a separate paint for every dot.
      for (const [shade, points] of waterPoints.entries()) {
        if (!points.length) continue;
        context.globalAlpha = ((shade + 0.5) / SHADES) * 0.6;
        context.beginPath();
        for (const point of points) {
          const x = point.x;
          let y =
            point.y +
            (point.swellSin * swellCos - point.swellCos * swellSin) *
              point.amplitude +
            (point.driftCos * driftCos - point.driftSin * driftSin) *
              height *
              0.012;

          for (const ripple of ripples) {
            const age = time - ripple.started;
            const distance = Math.hypot(x - ripple.x, y - ripple.y) / width;
            const front = distance - age * 0.18;
            y +=
              Math.sin(front * 55) *
              height *
              0.018 *
              Math.exp(-(front ** 2) / 0.003 - age * 0.9);
          }

          context.moveTo(x + point.radius, y);
          context.arc(x, y, point.radius, 0, Math.PI * 2);
        }
        context.fill();
      }
    };

    const tick = (now: number) => {
      elapsed.current += (now - lastTick) / 1000;
      lastTick = now;
      if (now - lastFrame >= frameInterval) {
        draw(elapsed.current);
        lastFrame = now - ((now - lastFrame) % frameInterval);
      }
      frame = requestAnimationFrame(tick);
    };

    const sync = () => {
      cancelAnimationFrame(frame);
      const reduced = motion.matches;
      if (reduced) ripples = [];
      canvas.dataset.motion = reduced
        ? "static"
        : visible && !document.hidden && !paused
          ? "running"
          : "paused";
      if (!visible || document.hidden) return;
      draw(reduced ? 0 : elapsed.current);
      if (!reduced && !paused) {
        lastTick = performance.now();
        lastFrame = lastTick;
        frame = requestAnimationFrame(tick);
      }
    };

    const resize = () => {
      const bounds = canvas.getBoundingClientRect();
      const nextRatio = Math.min(window.devicePixelRatio || 1, 1.25);
      if (
        width === bounds.width &&
        height === bounds.height &&
        pixelRatio === nextRatio
      )
        return;
      width = bounds.width;
      height = bounds.height;
      pixelRatio = nextRatio;
      canvas.width = Math.round(width * pixelRatio);
      canvas.height = Math.round(height * pixelRatio);
      buildPoints();
      sync();
    };

    const ripple = (event: PointerEvent) => {
      if (motion.matches || paused || !visible || variant !== "hero") return;
      const now = performance.now();
      if (
        event.type === "pointermove" &&
        (event.pointerType !== "mouse" || now - lastRipple < 550)
      )
        return;
      const bounds = canvas.getBoundingClientRect();
      ripples = [
        ...ripples.slice(-2),
        {
          x: event.clientX - bounds.left,
          y: event.clientY - bounds.top,
          started: elapsed.current,
        },
      ];
      lastRipple = now;
    };

    const intersection = new IntersectionObserver(
      ([entry]) => {
        visible = entry.isIntersecting;
        sync();
      },
      // The ambient canvas is fixed to the viewport, outside the scroller's
      // containing-block chain. Observe it against the viewport as well.
      { root: variant === "ambient" ? null : canvas.closest(".landing-page") },
    );
    const sizeObserver = new ResizeObserver(resize);
    const themeObserver = new MutationObserver(() => {
      color = getComputedStyle(canvas).color;
      sync();
    });
    intersection.observe(canvas);
    sizeObserver.observe(canvas);
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme", "data-appearance"],
    });
    motion.addEventListener("change", sync);
    document.addEventListener("visibilitychange", sync);
    hero.addEventListener("pointermove", ripple, { passive: true });
    hero.addEventListener("pointerdown", ripple, { passive: true });
    resize();

    return () => {
      cancelAnimationFrame(frame);
      intersection.disconnect();
      sizeObserver.disconnect();
      themeObserver.disconnect();
      motion.removeEventListener("change", sync);
      document.removeEventListener("visibilitychange", sync);
      hero.removeEventListener("pointermove", ripple);
      hero.removeEventListener("pointerdown", ripple);
    };
  }, [paused, variant]);

  return (
    <canvas
      ref={ref}
      className={cn("landing-particle-water", `landing-particle-${variant}`)}
      aria-hidden="true"
    />
  );
}
