## What does this change?

<!-- One or two sentences. Link the issue it fixes, if any: "Fixes #123". -->

## Screenshots

<!-- Required: at least one image of the render. Drag the files into this box.
     The "PR template" check fails without one.
     - Site fix: before and after, in dark and light.
     - Settings, widget or launcher change: the new look in DMS.
     - No visible change (docs, CI, backend): the browser or DMS with the change
       applied, showing that nothing looks different.
     No personal data: no real tabs, history, home path, user name or profile id. -->

## How was it tested?

- [ ] `python3 -B -m unittest discover -s tests/py -v` passes
- [ ] `sh tests/qml/run.sh` passes (QML changes)
- [ ] Tried in a running DMS session (describe below)

## Checklist

- [ ] Code, comments and identifiers are in English; user-visible strings go through `I18n.trFor` with an entry in `translations/fr.json`
- [ ] `browserglass.py` stays stdlib only, uses no network, and still runs as `python3 -I`
- [ ] Screenshots, logs and fixtures hold no personal data (no home path, user name, profile id, history or real tab)
- [ ] CHANGELOG.md updated under "Unreleased" for user-visible changes

### Site fix (`data/sites/`)

- [ ] Before / after screenshots above, in dark and light
- [ ] The page still reads well with the site scrolled under the fixed parts
