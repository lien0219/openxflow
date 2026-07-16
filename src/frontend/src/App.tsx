import "@xyflow/react/dist/style.css";
import { Suspense, useEffect } from "react";
import { RouterProvider } from "react-router-dom";
import { LoadingPage } from "./pages/LoadingPage";
import router from "./routes";
import { useDarkStore } from "./stores/darkStore";

export default function App() {
  const { dark, themePreset } = useDarkStore((state) => ({
    dark: state.dark,
    themePreset: state.themePreset,
  }));

  useEffect(() => {
    const body = document.getElementById("body");
    const root = document.documentElement;

    body?.classList.toggle("dark", dark);
    root.classList.toggle("dark", dark);
    root.dataset.theme = themePreset;
    root.dataset.appearance = dark ? "dark" : "light";
  }, [dark, themePreset]);

  return (
    <Suspense fallback={<LoadingPage />}>
      <RouterProvider router={router} />
    </Suspense>
  );
}
