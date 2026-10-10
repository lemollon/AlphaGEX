/**
 * Previously absent — Expo's bundled default (via @expo/metro-config's internal
 * transformer) covered plain babel-preset-expo with no project file. A project file
 * is now needed for one thing only: resolving the `@ironforge/shared/*` alias (#225,
 * the shared API types module in ../shared) at bundle time, same alias already
 * declared in tsconfig.json's "paths" for the type-checker. babel-preset-expo is
 * restated explicitly here because defining this file at all replaces Expo's
 * built-in default — omitting it would silently drop JSX/TS/Reanimated support.
 */
module.exports = function (api) {
  api.cache(true)
  return {
    presets: ['babel-preset-expo'],
    plugins: [
      [
        'module-resolver',
        {
          root: ['./'],
          alias: {
            '@ironforge/shared': '../shared',
          },
        },
      ],
    ],
  }
}
