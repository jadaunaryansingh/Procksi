import js from '@eslint/js'
import globals from 'globals'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    // Without this plugin ESLint cannot see that a symbol is used inside JSX,
    // so `motion` and `Icon` — referenced only as <motion.div> / <Icon /> —
    // were reported as unused in all 90 files that import them. main/ and
    // student/ had worked around it by naming `motion` in varsIgnorePattern,
    // which silences the symptom for one identifier and hides real dead code
    // for every other component.
    plugins: { react },
    settings: { react: { version: 'detect' } },
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    rules: {
      'react/jsx-uses-react': 'error',
      'react/jsx-uses-vars': 'error',
      // no-undef does NOT check identifiers used as JSX element names, only as
      // expressions: `{Icon}` is caught, `<Icon />` is not. A destructured prop
      // was dropped from FeatureCard while <Icon /> stayed in the body, and the
      // main site shipped a guaranteed "Icon is not defined" crash with lint
      // green. This rule is the JSX half of no-undef.
      'react/jsx-no-undef': 'error',
      'no-unused-vars': ['error', {
        // Components and constants are conventionally capitalised.
        varsIgnorePattern: '^[A-Z_]',
        // `catch (e)` with an unused binding is idiomatic, not a defect.
        caughtErrors: 'none',
        // Positional args that exist only to reach a later one, e.g. (_, i).
        args: 'after-used',
        argsIgnorePattern: '^_',
      }],
    },
  },
])
