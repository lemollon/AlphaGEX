# Git hooks

Enable once per clone:

    git config core.hooksPath .githooks

## `post-merge` — installs new frontend deps after a pull

Runs `npm install` when `frontend/package.json` changed, and reminds you to
`pip install` when the root `requirements.txt` changed.

## Removed: `pre-commit` (rebuilt the SpreadWorks bundle)

`spreadworks/frontend/dist` used to be a **tracked deploy artifact**, because
the live Render service built pip-only and served whatever was committed. A
`pre-commit` hook here rebuilt and staged `dist/` on every source commit, and
a CI job policed the ones that slipped past it.

As of 2026-08-19 the service's Build Command runs the frontend build itself:

    pip install --upgrade pip && pip install -r requirements.txt \
      && cd frontend && npm ci && npm run build

`dist/` is untracked and gitignored, so there is nothing left to keep fresh.
Keeping the hook would have been actively wrong — it would recreate the very
files the deploy now generates.
