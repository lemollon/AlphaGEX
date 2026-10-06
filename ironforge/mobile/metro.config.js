const { getDefaultConfig } = require('expo/metro-config')
const path = require('path')

/**
 * Previously absent — Expo's own default config was enough before this project
 * needed to reach outside its root. The #225 shared API types module lives at
 * ../shared (ironforge/shared), one level above this app's root; Metro only
 * watches/resolves files under its project root by default, so that directory
 * must be added to watchFolders explicitly or Metro reports it as an unresolvable
 * module the moment anything imports `@ironforge/shared/*` (the same alias
 * babel.config.js resolves and tsconfig.json declares for the type-checker).
 */
const config = getDefaultConfig(__dirname)

config.watchFolders = [...(config.watchFolders ?? []), path.resolve(__dirname, '../shared')]

module.exports = config
