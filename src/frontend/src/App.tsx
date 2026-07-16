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
  bloom: "light