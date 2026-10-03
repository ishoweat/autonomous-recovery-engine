import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",

  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./hooks/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}"
  ],

  theme: {
    extend: {
      colors: {
        "inverse-primary": "#22C55E",
        "on-error-container": "#F87171",
        "primary-fixed": "#4ADE80",
        "surface-bright": "#2A303C",
        "tertiary-fixed-dim": "#FCD34D",
        secondary: "#94A3B8",
        "surface-container-highest": "#1C2027",
        "surface-container-low": "#161A1F",
        "surface-container-high": "#1C2027",
        "on-background": "#F1F5F9",
        "inverse-surface": "#F1F5F9",
        surface: "#161A1F",
        "primary-fixed-dim": "#22C55E",
        "error-container": "rgba(248, 113, 113, 0.15)",
        error: "#F87171",
        "on-tertiary-fixed": "#0F1115",
        "on-secondary-fixed": "#0F1115",
        background: "#0F1115",
        "on-tertiary-container": "#FCD34D",
        "on-primary-container": "#F1F5F9",
        "surface-dim": "#161A1F",
        "on-secondary": "#F1F5F9",
        "outline-variant": "rgba(255, 255, 255, 0.08)",
        "secondary-container": "#1C2027",
        "primary-container": "rgba(74, 222, 128, 0.15)",
        outline: "rgba(255, 255, 255, 0.08)",
        "surface-container-lowest": "#0F1115",
        tertiary: "#FCD34D",
        "on-surface": "#F1F5F9",
        "tertiary-fixed": "#FCD34D",
        "surface-variant": "#1C2027",
        "on-primary": "#0F1115",
        "surface-tint": "#22C55E",
        "on-primary-fixed-variant": "#22C55E",
        "inverse-on-surface": "#0F1115",
        "on-tertiary-fixed-variant": "#FCD34D",
        "on-tertiary": "#0F1115",
        primary: "#22C55E",
        "tertiary-container": "rgba(252, 211, 77, 0.15)",
        "on-primary-fixed": "#0F1115",
        "on-secondary-fixed-variant": "#94A3B8",
        "secondary-fixed": "#38BDF8",
        "on-secondary-container": "#F1F5F9",
        "secondary-fixed-dim": "#38BDF8",
        "on-error": "#0F1115",
        "surface-container": "#161A1F",
        "on-surface-variant": "#94A3B8"
      },

      borderRadius: {
        DEFAULT: "0.125rem",
        lg: "0.25rem",
        xl: "0.5rem",
        full: "0.75rem"
      },

      spacing: {
        "space-2xl": "3rem",
        "gutter-desktop": "1.5rem",
        gutter: "1rem",
        "space-xl": "2rem",
        "margin-desktop": "2.5rem",
        "space-xs": "0.25rem",
        "space-sm": "0.5rem",
        margin: "1rem",
        "space-md": "1rem",
        "space-lg": "1.5rem",
        "space-2xs": "0.125rem"
      },

      fontFamily: {
        "headline-lg": ["Space Grotesk", "sans-serif"],
        "body-sm": ["Inter", "sans-serif"],
        "label-badge": ["JetBrains Mono", "monospace"],
        "mono-metric": ["JetBrains Mono", "monospace"],
        "display-hero": ["Space Grotesk", "sans-serif"],
        "headline-md": ["Space Grotesk", "sans-serif"],
        "body-md": ["Inter", "sans-serif"],
        "body-lg": ["Inter", "sans-serif"],
        "headline-xl": ["Space Grotesk", "sans-serif"],
        "mono-code": ["JetBrains Mono", "monospace"],
        "headline-xl-mobile": ["Space Grotesk", "sans-serif"],
        "label-caps": ["JetBrains Mono", "monospace"],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "monospace"
        ]
      },

      fontSize: {
        "headline-lg": [
          "24px",
          { lineHeight: "32px", letterSpacing: "-0.01em", fontWeight: "600" }
        ],
        "body-sm": [
          "12px",
          { lineHeight: "18px", fontWeight: "400" }
        ],
        "label-badge": [
          "10px",
          { lineHeight: "14px", letterSpacing: "0em", fontWeight: "400" }
        ],
        "mono-metric": [
          "28px",
          { lineHeight: "32px", letterSpacing: "-0.01em", fontWeight: "500" }
        ],
        "display-hero": [
          "56px",
          { lineHeight: "64px", letterSpacing: "-0.01em", fontWeight: "600" }
        ],
        "headline-md": [
          "18px",
          { lineHeight: "26px", letterSpacing: "0em", fontWeight: "600" }
        ],
        "body-md": [
          "14px",
          { lineHeight: "20px", fontWeight: "400" }
        ],
        "body-lg": [
          "16px",
          { lineHeight: "24px", fontWeight: "400" }
        ],
        "headline-xl": [
          "36px",
          { lineHeight: "44px", letterSpacing: "-0.02em", fontWeight: "600" }
        ],
        "mono-code": [
          "13px",
          { lineHeight: "20px", fontWeight: "400" }
        ],
        "headline-xl-mobile": [
          "28px",
          { lineHeight: "36px", letterSpacing: "-0.02em", fontWeight: "600" }
        ],
        "label-caps": [
          "11px",
          { lineHeight: "16px", letterSpacing: "0em", fontWeight: "400" }
        ]
      },

      animation: {
        "pulse-soft": "pulse-soft 2s ease-in-out infinite",
        scan: "scan 2.5s linear infinite"
      },

      keyframes: {
        "pulse-soft": {
          "0%, 100%": {
            opacity: "0.55"
          },
          "50%": {
            opacity: "1"
          }
        },

        scan: {
          "0%": {
            transform: "translateY(-100%)"
          },
          "100%": {
            transform: "translateY(100%)"
          }
        }
      }
    }
  },

  plugins: []
};

export default config;
