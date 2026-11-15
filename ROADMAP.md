# Roadmap

These are ideas, not promises, and they have no dates. Anything that would need the network while the plugin runs, or would send data somewhere, is out of scope.

## Planned

- **New screenshots**: a GIF of the launcher, and the *Sites* settings with the new page layers.
- **Live control in Flatpak and Snap browsers**: through the WebExtensions portal or a path shared with the sandbox, since the helper cannot run inside it today.
- **Live control checked on Zen, Floorp and Waterfox**: it is built for every Firefox-family browser but tested on Firefox and LibreWolf only.
- **Live control in frames** (`all_frames`): today only the main page switches at once; frames follow at the next restart.
- **Snap Firefox in the niri rule**: add the Snap app-id (`firefox_firefox`) once it is confirmed on a real Snap install. Until then, see *Known limits*.
- **Live checks on more installs**: Zen, Floorp and Waterfox, plus the Flatpak and Snap variants. Their profile folders come from the browsers' documentation and are tested on a fake home only.
- **Dark pages decided by the helper**: send the *Dark pages* setting with the excluded sites, so the companion darkens only when the helper says so. Today, under a dark theme, a page can set the colour variables itself and switch the darkening on while *Dark pages* is off (what Dark Reader then fetches is limited to stylesheets, without cookies).
- **Dark Reader and local addresses**: its stylesheet fetch runs with the add-on's access, so a page that links a stylesheet on the local network or on `localhost` gets its text copied in. Refuse loopback and private targets (and redirects to them).
- **Exclude copied URL and private suffixes**: `www.` is kept before country suffixes such as `gov.uk`, but not yet before private ones such as `github.io`; the helper, which has the Public Suffix List, could reduce the host instead.
- **Light mode in the end-to-end test**: reader view and PDFs are checked in dark mode only (`tests/e2e/`).
- **Choose the profiles**: an option to leave some profiles of a browser without glass.
- **The DMS plugin registry**: submit the plugin once it has had wider use.

## Not planned

- **Chromium-based browsers**: they have no `userChrome.css` or `userContent.css` to paint the window and the pages with.
- **Restarting the browser automatically**: that would close your windows and tabs. The badge and the toast say when a restart is needed, and you choose when to restart.
- **Downloading styles at run time**: the my-internet styles are bundled in `data/` and refreshed through a pull request (see [CONTRIBUTING.md](CONTRIBUTING.md#releasing-a-version)).
- **Compositors other than niri**: the glass depends on a niri window rule.

## Known limits

- **A manual restart is needed.** Firefox reads its CSS only when it starts. After a change (a new wallpaper, the opacity, a setting), a running browser shows the new look only after a restart. When the glass turns on, niri applies the plugin's rule at once, so a running browser stays opaque until its restart. The exceptions: the light or dark switch (with DMS's *Sync with portal* on), and site exclusions with Live control.
- **`gs on` and `gs off` are not live**: the browser's own bars are read at start-up, so they follow at the next restart; the niri rule changes at once.
- **Development checkouts use the unsigned add-on.** Without a signed `companion/browserglass@companion.xpi` that matches `extension/` (a repository clone, or `extension/` changed after signing), Browser Glass falls back to the unsigned companion, as in 1.2: Firefox release, ESR and Beta builds refuse it, so there the launcher's changes apply at the next restart, and LibreWolf shows it as *could not be verified*. Released versions ship the signed add-on.
- **Private windows have no live control**: the companion does not run there and their site cannot be read, so `gs blist` refuses in a private window, and a private window shows exclusion changes after a restart.
- **Frames follow at the next restart**: the companion switches the main page only (no `all_frames`).
- **Shadow trees follow at the next restart**: a live exclusion leaves the parts a site draws in its shadow DOM styled until the browser restarts, since they do not see the page's `data-browserglass-off` mark.
- **Shadow trees cannot tell a light page from a dark one**: the parts a site draws in its shadow DOM do not see the page's dark-version markers or the companion's tone mark. Under a dark theme the generic style therefore leaves them alone on every page (as in 1.0), and a dedicated site style still applies there on every page, light-only ones included.
- **Launcher results come after the apps** whose name matches the query, ten lines at most, since the plugin answers in the launcher's *all* mode instead of having a mode of its own.
- **The current site can lag without the companion**: the browser's saved session is about 15 s behind, up to an hour after 3 minutes of system idle.
- **Firefox family only**: there is no Chromium support (see *Not planned*).
- **The niri rule covers the whole app-id.** It matches every window of `firefox`, `librewolf`, `zen` and the rest. A profile without glass, started with `-profile` for instance, is also shown fully opaque instead of following DMS's global opacity.
- **Zen has not been tested live.** Its profile folders and its transparency-mod warning are tested on fixtures only.
- **Flatpak and Snap**: Snap Firefox is not in the niri rule, because its app-id could not be confirmed. Snap Firefox therefore gets the CSS tint and DMS's global opacity together, and looks more transparent than intended. No Flatpak or Snap install has been tried live. A profile outside the known profile folders is not found.
- **Opacity source**: browserGlass reads the opacity of the *first* global window rule (one without `match`) in DMS's `niri/dms/windowrules.kdl`, but niri applies the *last* one. If several global rules set different opacities, the browser can differ from your other windows. Use the opacity override in *Appearance* in that case.
- **A cleaner that waits too long gives up.** When you uninstall while a browser runs, a detached cleaner waits for that browser to close before it puts the prefs back in `prefs.js`. It polls for 7 days at most. After that it leaves its job in the state folder's `pending/` directory, and the next uninstall finishes it. Until then the browser keeps the plugin's pref values.
- **An unreadable profile lock keeps the niri rule.** When a profile's `.parentlock` exists but cannot be probed (permissions or an unusual file system), the profile counts as possibly running. Turning the glass off then keeps the plugin's niri rule, and *Status* shows it as held, until the lock can be read.
- The running-browser check reads the lock with the `struct flock` layout of x86_64 and aarch64 glibc.
- After a plugin update, run `dms restart`: DMS keeps the plugin's JavaScript and component files cached, so a reload alone may still run the old code.
