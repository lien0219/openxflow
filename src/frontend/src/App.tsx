import "@xyflow/react/dist/style.css";
import { Suspense, useEffect } from "react";
import { RouterProvider } from "react-router-dom";
import { LoadingPage } from "./pages/LoadingPage";
import router from "./routes";
import { useDarkStore } from "./stores/darkStore";

const PRESET_APPEARANCE = {
  nebula: "dark",
  polar: "light",
  terminal: "dark",
  bloom: "light",
  aurora: "dark",
} as const;

export default function App() {
  const { dark, themePreset } = useDarkStore((state) => ({
    dark: state.dark,
    themePreset: state.themePreset,
  }));

  useEffect(() => {
    const body = document.getElementById("body");
    const root = document.documentElement;
    const presetAppearance =
      themePreset === "classic" ? undefined : PRESET_APPEARANCE[themePreset];
    const resolvedDark = presetAppearance ? presetAppearance === "dark" : dark;

    body?.classList.toggle("dark", resolvedDark);
    root.classList.toggle("dark", resolvedDark);
    root.dataset.theme = themePreset;
    root.dataset.appearance = resolvedDark ? "dark" : "light";
  }, [dark, themePreset]);

  return (
    <Suspense fallback={<LoadingPage />}>
      <RouterProvider router={router} />
    </Suspense>
  );
}
