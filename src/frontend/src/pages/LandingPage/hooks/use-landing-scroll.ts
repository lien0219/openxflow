import {
  type RefObject,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

export function useLandingScroll(ref: RefObject<HTMLDivElement | null>) {
  const [compact, setCompact] = useState(false);
  const [activeSection, setActiveSection] = useState("main-content");
  const navigationTarget = useRef<string | null>(null);
  const selectSection = useCallback((id: string) => {
    navigationTarget.current = id;
    setActiveSection(id);
  }, []);
  useEffect(() => {
    const container = ref.current;
    if (!container) return;
    let lastY = container.scrollTop;
    let frame = 0;
    let lastProgress = "";
    const heroContent = container.querySelector<HTMLElement>(
      ".landing-hero-content",
    );
    const sections = ["main-content", "workflow", "capabilities"].map((id) =>
      container.querySelector<HTMLElement>(`#${id}`),
    );
    const update = () => {
      const y = container.scrollTop;
      if (y < 64) setCompact(false);
      else if (Math.abs(y - lastY) > 8) setCompact(y > lastY);
      if (Math.abs(y - lastY) > 8 || y < 64) lastY = y;
      const top = container.getBoundingClientRect().top;
      const maxScroll = Math.max(
        0,
        container.scrollHeight - container.clientHeight,
      );
      const atBottom = maxScroll > 0 && maxScroll - y <= 2;
      const target = sections.find(
        (section) => section?.id === navigationTarget.current,
      );
      if (target) {
        const margin =
          Number.parseFloat(getComputedStyle(target).scrollMarginTop) || 0;
        const destination = Math.min(
          maxScroll,
          Math.max(0, y + target.getBoundingClientRect().top - top - margin),
        );
        setActiveSection(target.id);
        if (Math.abs(y - destination) <= 2) navigationTarget.current = null;
      } else if (maxScroll > 0) {
        let active = "main-content";
        for (const section of sections) {
          if (section && section.getBoundingClientRect().top - top < 240)
            active = section.id;
        }
        // The final section cannot reach the header's threshold on tall screens.
        if (atBottom) active = "capabilities";
        setActiveSection(active);
      }
      const progress = Math.min(y / 600, 1).toFixed(3);
      if (progress !== lastProgress) {
        heroContent?.style.setProperty("--landing-scroll", progress);
        lastProgress = progress;
      }
    };
    const scroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    };
    const selectHash = () => {
      const id = window.location.hash.slice(1) || "main-content";
      if (sections.some((section) => section?.id === id)) selectSection(id);
      scroll();
    };
    const interruptNavigation = (event: Event) => {
      if (
        event instanceof KeyboardEvent &&
        ![
          "ArrowUp",
          "ArrowDown",
          "PageUp",
          "PageDown",
          "Home",
          "End",
          " ",
        ].includes(event.key)
      )
        return;
      navigationTarget.current = null;
      scroll();
    };
    container.addEventListener("scroll", scroll, { passive: true });
    container.addEventListener("wheel", interruptNavigation, { passive: true });
    container.addEventListener("touchstart", interruptNavigation, {
      passive: true,
    });
    container.addEventListener("pointerdown", interruptNavigation, {
      passive: true,
    });
    container.addEventListener("keydown", interruptNavigation);
    window.addEventListener("hashchange", selectHash);
    const resizeObserver = new ResizeObserver(scroll);
    resizeObserver.observe(container);
    for (const section of sections)
      if (section) resizeObserver.observe(section);
    if (window.location.hash) selectHash();
    update();
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            (entry.target as HTMLElement).dataset.visible = "true";
            observer.unobserve(entry.target);
          }
        }
      },
      { root: container, threshold: 0.12 },
    );
    const reveals = container.querySelectorAll<HTMLElement>("[data-reveal]");
    if (!media.matches) {
      for (const element of reveals) {
        element.dataset.visible = "false";
        observer.observe(element);
      }
    }
    const revealAll = () => {
      if (!media.matches) return;
      observer.disconnect();
      for (const element of reveals) element.dataset.visible = "true";
    };
    media.addEventListener("change", revealAll);
    return () => {
      cancelAnimationFrame(frame);
      container.removeEventListener("scroll", scroll);
      container.removeEventListener("wheel", interruptNavigation);
      container.removeEventListener("touchstart", interruptNavigation);
      container.removeEventListener("pointerdown", interruptNavigation);
      container.removeEventListener("keydown", interruptNavigation);
      window.removeEventListener("hashchange", selectHash);
      media.removeEventListener("change", revealAll);
      resizeObserver.disconnect();
      observer.disconnect();
    };
  }, [ref, selectSection]);
  return { compact, activeSection, selectSection };
}
