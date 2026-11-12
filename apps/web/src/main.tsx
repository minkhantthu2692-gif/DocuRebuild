import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { initI18n } from "./i18n";
import { applyCachedAppearance } from "./lib/appearance";

import "./index.css";
// Local KaTeX stylesheet and fonts; math never needs a network request.
import "katex/dist/katex.min.css";

applyCachedAppearance();
initI18n();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
