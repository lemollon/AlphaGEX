# Git hooks

Enable once per clone:

    git config core.hooksPath .githooks

## `pre-commit` — rebuilds the SpreadWorks bundle

`spreadworks/frontend/dist` is a **tracked deploy artifact**. The live Render
service (`srv-d6mv30f5gffc73bog9a0`) builds with:

    pip install --upgrade pip && pip install -r requirements.txt

There is no npm step, so **whatever is committed under `dist/` is exactly what
production serves**. Render's API cannot change a service's build command, so
this is enforced here instead.

The hook rebuilds and stages `dist/` automatically whenever anything under
`spreadworks/frontend/src/` is committed. It is a build, not a warning: there
is no step for anyone to remember, and no way to commit source without the
bundle following it.

CI (`spreadworks-dist`) is the backstop for commits made without the hook —
e.g. `--no-verify`, the GitHub web UI, or a clone that never ran the config
line above.
