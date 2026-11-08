/**
 * Shared Tailwind preset for DocuRebuild.
 * Every value maps back to a CSS design token in ./src/tokens.css.
 * Do not add raw palette values here; add a token instead.
 */
const preset = {
  darkMode: ["class"],
  theme: {
    extend: {
      colors: {
        background: "hsl(var(--background) / <alpha-value>)",
        foreground: "hsl(var(--foreground) / <alpha-value>)",
        card: {
          DEFAULT: "hsl(var(--card) / <alpha-value>)",
          foreground: "hsl(var(--card-foreground) / <alpha-value>)",
        },
        popover: {
          DEFAULT: "hsl(var(--popover) / <alpha-value>)",
          foreground: "hsl(var(--popover-foreground) / <alpha-value>)",
        },
        primary: {
          DEFAULT: "hsl(var(--primary) / <alpha-value>)",
          foreground: "hsl(var(--primary-foreground) / <alpha-value>)",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary) / <alpha-value>)",
          foreground: "hsl(var(--secondary-foreground) / <alpha-value>)",
        },
        muted: {
          DEFAULT: "hsl(var(--muted) / <alpha-value>)",
          foreground: "hsl(var(--muted-foreground) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "hsl(var(--accent) / <alpha-value>)",
          foreground: "hsl(var(--accent-foreground) / <alpha-value>)",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive) / <alpha-value>)",
          foreground: "hsl(var(--destructive-foreground) / <alpha-value>)",
        },
        success: {
          DEFAULT: "hsl(var(--success) / <alpha-value>)",
          foreground: "hsl(var(--success-foreground) / <alpha-value>)",
        },
        warning: {
          DEFAULT: "hsl(var(--warning) / <alpha-value>)",
          foreground: "hsl(var(--warning-foreground) / <alpha-value>)",
        },
        info: {
          DEFAULT: "hsl(var(--info) / <alpha-value>)",
          foreground: "hsl(var(--info-foreground) / <alpha-value>)",
        },
        border: "hsl(var(--border) / <alpha-value>)",
        input: "hsl(var(--input) / <alpha-value>)",
        ring: "hsl(var(--ring) / <alpha-value>)",
        glass: {
          DEFAULT: "hsl(var(--glass-surface) / var(--glass-opacity))",
          strong: "hsl(var(--glass-surface) / var(--glass-strong-opacity))",
          tint: "hsl(var(--glass-tint) / <alpha-value>)",
        },
      },
      borderRadius: {
        xs: "var(--radius-xs)",
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
        "2xl": "var(--radius-2xl)",
        pill: "var(--radius-pill)",
      },
      fontFamily: {
        ui: "var(--font-ui)",
        document: "var(--font-document)",
        mono: "var(--font-mono)",
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      spacing: {
        header: "var(--header-height)",
        statusbar: "var(--statusbar-height)",
        panel: "var(--panel-header-height)",
        control: "var(--control-height)",
      },
      height: {
        header: "var(--header-height)",
        statusbar: "var(--statusbar-height)",
        panel: "var(--panel-header-height)",
        control: "var(--control-height)",
        "control-sm": "var(--control-height-sm)",
        "control-lg": "var(--control-height-lg)",
        "control-xs": "var(--control-height-xs)",
      },
      minHeight: {
        control: "var(--control-height)",
      },
      width: {
        icon: "var(--icon)",
        control: "var(--control-height)",
        "control-sm": "var(--control-height-sm)",
        "control-lg": "var(--control-height-lg)",
        "control-xs": "var(--control-height-xs)",
      },
      size: {
        icon: "var(--icon)",
        "icon-sm": "var(--icon-sm)",
        "icon-lg": "var(--icon-lg)",
      },
      maxWidth: {
        page: "var(--page-max-width)",
        content: "var(--content-max-width)",
      },
      boxShadow: {
        xs: "var(--shadow-xs)",
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        glow: "var(--shadow-glow)",
      },
      transitionTimingFunction: {
        out: "var(--ease-out)",
        standard: "var(--ease-standard)",
      },
      transitionDuration: {
        fast: "var(--duration-fast)",
        base: "var(--duration-base)",
        slow: "var(--duration-slow)",
      },
      zIndex: {
        header: "var(--z-header)",
        overlay: "var(--z-overlay)",
        toast: "var(--z-toast)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(0.5rem)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.97)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-in": "fade-in var(--duration-base) var(--ease-out)",
        "slide-up": "slide-up var(--duration-base) var(--ease-out)",
        "scale-in": "scale-in var(--duration-fast) var(--ease-out)",
        shimmer: "shimmer 1.6s infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

module.exports = preset;
