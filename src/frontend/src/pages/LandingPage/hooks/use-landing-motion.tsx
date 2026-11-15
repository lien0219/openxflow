import {
  createContext,
  type PropsWithChildren,
  type RefObject,
  useContext,
  useEffect,
  useState,
} from "react";

const LandingMotionContext = createContext({
  paused: false,
  reducedMotion: false,
  documentVisible: true,
  togglePaused: () => {},
});

export function LandingMotionProvider({ children }: PropsWithChildren) {
  const [paused, setPaused] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [documentVisible, setDocumentVisible] = useState(
    () => !document.hidden,
  );

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const syncMotion = () => setReducedMotion(media.matches);
    const syncVisibility = () => setDocumentVisible(!document.hidden);
    media.addEventListener("change", syncMotion);
    document.addEventListener("visibilitychange", syncVisibility);
    return () => {
      media.removeEventListener("change", syncMotion);
      document.removeEventListener("visibilitychange", syncVisibility);
    };
  }, []);

  return (
    <LandingMotionContext.Provider
      value={{
        paused,
        reducedMotion,
        documentVisible,
        togglePaused: () => setPaused((value) => !value),
      }}
    >
      {children}
    </LandingMotionContext.Provider>
  );
}

export const useLandingMotion = () => useContext(LandingMotionContext);

export function useVisibleMotion(ref: RefObject<HTMLElement | null>) {
  const { paused, reducedMotion, documentVisible } = useLandingMotion();
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new IntersectionObserver(
      ([entry]) => setVisible(entry.isIntersecting),
      { root: element.closest(".landing-page"), threshold: 0.08 },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);

  return reducedMotion
    ? "static"
    : visible && documentVisible && !paused
      ? "running"
      : "paused";
}

export function usePipelinePlayback(
  ref: RefObject<HTMLElement | null>,
  resetKey = "default",
) {
  const motion = useVisibleMotion(ref);
  const [playback, setPlayback] = useState({ key: resetKey, stage: 0 });

  useEffect(() => {
    setPlayback({ key: resetKey, stage: 0 });
  }, [resetKey]);

  useEffect(() => {
    if (motion !== "running") return;
    const timer = window.setInterval(() => {
      setPlayback((current) => ({
        key: resetKey,
        stage: (current.stage + 1) % 4,
      }));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [motion, resetKey]);

  return {
    motion,
    stage:
      motion === "static" ? 3 : playback.key === resetKey ? playback.stage : 0,
  };
}
