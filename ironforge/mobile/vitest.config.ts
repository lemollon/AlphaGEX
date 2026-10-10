import { defineConfig } from 'vitest/config'
import path from 'node:path'

/**
 * `npm test` has exited 1 since this package existed — vitest was a dependency, the
 * script was wired, and there were no test files and no config, so every run failed with
 * "No test files found". A suite that has never run is indistinguishable from one that
 * does not exist.
 *
 * Scope is deliberately the PURE modules: the rules that decide what a number means.
 * There is no React Native renderer here and adding one (jest-expo, RNTL, a full native
 * mock surface) is a separate decision — component rendering is not what has been going
 * wrong. What has been going wrong is logic that silently produces a plausible wrong
 * answer: a chart that crops out breakeven, an account attributed to the wrong agent,
 * paper money added to real money.
 */
export default defineConfig({
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
