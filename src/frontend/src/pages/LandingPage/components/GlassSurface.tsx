import { type ReactNode, useEffect, useRef } from "react";

export default function GlassSurface({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const surface = ref.current;
    if (!surface) return;
    const media = window.matchMedia(
      "(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)",
    );
    let frame = 0;
    let pointerX = 0;
    let pointerY = 0;
    const reset = () => {
      cancelAnimationFrame(frame);
      frame = 0;
      surface.style.removeProperty("--glass-x");
      surface.style.removeProperty("--glass-y");
      surface.style.removeProperty("--glass-rotate-x");
      surface.style.removeProperty("--glass-rotate-y");
    };
    const move = (event: PointerEvent) => {
      if (!media.matches) return;
      pointerX = event.clientX;
      pointerY = event.clientY;
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        const { left, top, width, height } = surface.getBoundingClientRect();
        if (!width || !height) return;
        const x = (pointerX - left) / width;
        const y = (pointerY - top) / height;
        surface.style.setProperty("--glass-x", `${x * 100}%`);
        surface.style.setProperty("--glass-y", `${y * 100}%`);
        surface.style.setProperty("--glass-rotate-x", `${(0.5 - y) * 4}deg`);
        surface.style.setProperty("--glass-rotate-y", `${(x - 0.5) * 4}deg`);
      });
    };
    surface.addEventListener("pointermove", move, { passive: true });
    surface.addEventListener("pointerleave", reset);
    media.addEventListener("change", reset);
    return () => {
      reset();
      surface.removeEventListener("pointermove", move);
      surface.removeEventListener("pointerleave", reset);
      media.removeEventListener("change", reset);
    };
  }, []);
  return (
    <div ref={ref} className={`landing-glass landing-interactive ${className}`}>
      {children}
    </div>
  );
}
