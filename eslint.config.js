import globals from "globals";

/** @type {import("eslint").Linter.Config[]} */
export default [
  {
    ignores: [
      "node_modules/**",
      ".venv*/**",
      "_staged_unused_review/**",
      "static/js/procurement/**", // extracted gradually; lint once modules stabilize
    ],
  },
  {
    files: ["static/js/**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: {
        ...globals.browser,
        ...globals.es2021,
      },
    },
    rules: {
      // Complexity / nesting — the three standards we enforce
      complexity: ["warn", 15],
      "max-depth": ["warn", 3],
      "max-lines-per-function": ["warn", { max: 80, skipBlankLines: true, skipComments: true }],
      "no-nested-ternary": "warn",

      // Hygiene (keep light so day-one is usable)
      "no-undef": "error",
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "no-var": "warn",
      "prefer-const": "warn",
    },
  },
  // Known monoliths — warn-only baseline; tighten as Phase 3 lands.
  {
    files: [
      "static/js/orderQuotation.js",
      "static/js/adminViewQuotations.js",
      "static/js/updateQuotation.js",
      "static/js/viewQuotation.js",
    ],
    rules: {
      complexity: "off",
      "max-depth": "off",
      "max-lines-per-function": "off",
      "no-nested-ternary": "off",
    },
  },
];
