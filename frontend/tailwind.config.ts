/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    colors: {
      // Old Money Design System
      primary: "#1F3A2C",
      secondary: "#7B8271",
      tertiary: "#B89155",
      neutral: "#F0EADB",
      surface: "#F8F1DF",

      // Neutrals
      white: "#FFFFFF",
      black: "#000000",

      // Grays for borders, backgrounds
      gray: {
        50: "#FAFAF8",
        100: "#F5F5F1",
        200: "#EFEFEA",
        300: "#E8E8E0",
        400: "#D4D4CC",
        500: "#BFBFB5",
        600: "#9B9B91",
        700: "#7B7B71",
        800: "#5A5A50",
        900: "#3A3A30",
      },

      // Status colors
      success: "#4CAF50",
      error: "#F44336",
      warning: "#FF9800",
      info: "#2196F3",
    },
    fontFamily: {
      display: ["Cormorant", "serif"],
      body: ["EB Garamond", "serif"],
      label: ["Inter", "sans-serif"],
    },
    spacing: {
      0: "0",
      sm: "8px",
      md: "16px",
      lg: "32px",
      px: "1px",
      1: "4px",
      2: "8px",
      3: "12px",
      4: "16px",
      6: "24px",
      8: "32px",
      12: "48px",
      16: "64px",
    },
    borderRadius: {
      none: "0",
      sm: "0px",
      md: "2px",
      lg: "4px",
      full: "9999px",
    },
    fontSize: {
      xs: "0.75rem",
      sm: "0.875rem",
      base: "1rem",
      lg: "1.125rem",
      xl: "1.25rem",
      "2xl": "1.5rem",
      "3xl": "1.875rem",
      "4xl": "2.25rem",
      "5xl": "3rem",
      display: "5rem",
    },
    lineHeight: {
      tight: "1.2",
      normal: "1.5",
      relaxed: "1.625",
      body: "1.7",
    },
  },
  plugins: [],
}

