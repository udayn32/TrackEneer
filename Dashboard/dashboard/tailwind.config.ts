// tailwind.config.ts

import type { Config } from 'tailwindcss'

const config: Config = {
  // This is the part to double-check. These paths must be correct.
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}', // This line is especially important for you
  ],
  darkMode: "class",
  theme: {
    extend: {},
  },
  plugins: [],
}
export default config