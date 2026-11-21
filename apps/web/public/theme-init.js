/*
 * Apply cached appearance before first paint to avoid a theme flash.
 * Loaded as a blocking external script so the desktop shell can use a strict
 * Content-Security-Policy without allowing inline scripts.
 */
(function () {
  try {
    var raw = localStorage.getItem("docurebuild.appearance");
    var appearance = raw ? JSON.parse(raw) : null;
    var root = document.documentElement;
    if (appearance) {
      root.dataset.accent = appearance.accent || "indigo";
      root.dataset.radius = appearance.radius || "soft";
      root.dataset.blur = appearance.blur || "subtle";
      root.dataset.density = appearance.density || "comfortable";
      root.dataset.fontSize = appearance.font_size || "md";
      root.dataset.motion = appearance.motion || "full";
      var systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      var dark = appearance.theme === "dark" || (appearance.theme !== "light" && systemDark);
      root.classList.toggle("dark", dark);
    } else {
      var prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      root.classList.toggle("dark", prefersDark);
    }
    var language = localStorage.getItem("docurebuild.language");
    if (language === "en" || language === "my") {
      root.lang = language;
    }
  } catch (error) {
    /* A corrupted cache must never block startup. */
  }
})();
