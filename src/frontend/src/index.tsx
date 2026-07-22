import "./i18n";
import ReactDOM from "react-dom/client";
import { detectedLang, loadLanguage } from "./i18n";
import reportWebVitals from "./reportWebVitals";

import "./style/classes.css";
// @ts-ignore
import "./style/index.css";
import "./style/themes.css";
import "./style/themes-enhanced.css";
import "./style/themes-scenes.css";
import "./style/themes-components.css";
// @ts-ignore
import "./App.css";
import "./style/applies.css";

// @ts-ignore
import App from "./customization/custom-App";

loadLanguage(detectedLang).then(() => {
  const root = ReactDOM.createRoot(
    document.getElementById("root") as HTMLElement,
  );
  root.render(<App />);
  reportWebVitals();
});
