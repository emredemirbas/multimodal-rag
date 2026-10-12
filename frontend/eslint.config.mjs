import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypeScript from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTypeScript,
  {
    files: ["tooling/next-lint-glob/index.cjs"],
    rules: {
      "@typescript-eslint/no-require-imports": ["error", { allow: ["^node:", "^tinyglobby$"] }],
    },
  },
  globalIgnores([".next/**", "coverage/**", "next-env.d.ts"]),
]);
