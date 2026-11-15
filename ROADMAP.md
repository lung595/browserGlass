# Roadmap

These are ideas, not promises, and they have no dates. Anything that would need the network while the plugin runs, or would send data somewhere, is out of scope.

## Planned

- **Signed companion add-on** (next version with signing keys): have Mozilla sign the companion and ship it as `companion/browserglass@companion.xpi`, so *Live control* works on Firefox release, ESR and Beta builds, LibreWolf shows it as verified, and `xpinstall.signatures.required` is no longer written. 1.3.0 to 1.3.3 support it but ship the unsigned add-on.
- **New screenshots**: a GIF of the launcher, and the *Sites* settings with the new page layers.
- **Live control in Flatpak and Snap browsers**: through the WebExtensions portal or a path shared with the sandbox, since the helper cannot run inside it today.
- **Live control checked on Zen, Floorp and Waterfox**: it is built for every Firefox-family browser but tested on Firefox and LibreWolf only.
- **Glass in frames**: since 1.3.1 every frame keeps its own background (the add-on marks it excluded), so its text stays readable; giving frames the glass would need their own tone and layers.
- **Snap Firefox in the niri rule**: add the Snap app-id (`firefox_firefox`) once it is confirmed on a real Snap install. Until then, see *Known limits*.
- **Live checks on more installs**: Zen, Floorp and Waterfox, plus the Flatpak and Snap variants. Their profile folders come from the browsers' documentation and are tested on a fake home only.
- **Dark Reader and local addresses**: its stylesheet fetch runs with the add-on's access, so a page that links a stylesheet on the local network or on `localhost` gets its text copied in. Refuse loopback and private targets (and redirects to them).
- **Hosts written with a final dot** (`example.org.`): live exclusions and per-site blocks do not match them yet; the URL lookaheads should accept an optional final dot.
- **Waterfox's own defaults for the add-on signature guard**: the guard assumes Firefox's defaults for every family; use per-family defaults once Waterfox's are confirmed in its source.
- **Unreadable `prefs.js`**: a read error is taken as an empty file today; warn and skip the profile instead, so no original value is recorded as absent by mistake.
- **Contract `report.txt` fixture**: regenerate it from a real run and list every line in `schema.json` (`report_lines`); describe the daemon's real triggers and its 10 s poll in CONTRIBUTING.
- **Lighter companion script**: handle `scroll` once per frame at most and group the tone checks that follow changes on `<html>`; load Dark Reader only in the pages it darkens.
- **Light mode in the end-to-end test**: reader view and PDFs are checked in dark mode only (`tests/e2e/`).
- **Choose the profiles**: an option to leave some profiles of a browser without glass.
- ~~**Site theme presets**~~ (done in 1.4): under a dark theme the add-on writes a site's own stored theme value (a generic rule for common storage keys, recipes per site in `data/themes.json`, cookies included) and puts it back afterwards. Still out of reach: a signed-in account whose theme comes from the server (a recipe skips the write), cookies the site sets `HttpOnly`, and a stored choice of the default that cannot be told from no choice at all. See *Sites with their own theme menu* in the [user guide](docs/GUIDE.md#light-pages-under-a-dark-theme).
- **The DMS plugin registry**: submit the plugin once it has had wider use.

## Not planned

- **Chromium-based browsers**: they have no `userChrome.css` or `userContent.css` to paint the window and the pages with.
- **Restarting the browser automatically**: that would close your windows and tabs. The badge and the toast say when a restart is needed, and you choose when to restart.
- **Downloading styles at run time**: the my-internet styles are bundled in `data/` and refreshed through a pull request (see [CONTRIBUTING.md](CONTRIBUTING.md#releasing-a-version)).
- **Compositors other than niri**: the glass depends on a niri window rule.

## Known limits

- **A manual restart is needed.** Firefox reads its CSS only when it starts. After a change (a new wallpaper, the opacity, a setting), a running browser shows the new look only after a restart. When the glass turns on, niri applies the plugin's rule at once, so a running browser stays opaque until its restart. The exceptions: the light or dark switch (with DMS's *Sync with portal* on), and site exclusions with Live control.
- **`gs on` and `gs off` are not live**: the browser's own bars are read at start-up, so they follow at the next restart; the niri rule changes at once.
- **Live control needs an add-on that loads unsigned** (until it is signed). Without a signed `companion/browserglass@companion.xpi` that matches `extension/` (1.3.0 to 1.3.3 ship none), Browser Glass places the unsigned companion and sets `xpinstall.signatures.required` to `false`, as in 1.2: Firefox release, ESR and Beta builds refuse it, so there the launcher's changes apply at the next restart, and LibreWolf shows it as *could not be verified*.
- **Private windows have no live control**: the companion does not run there and their site cannot be read, so `gs blist` refuses in a private window, and a private window shows exclusion changes after a restart.
- **Frames stay opaque**: with Live control, frames inside a page (a captcha, an embedded video or form) keep their own background; without it they follow the generic rule.
- **Bars laid in the flow**: a web app's sidebar or header that is neither fixed nor sticky keeps its own colours (no uniform veil), since it cannot be told from a panel of the page.
- **Text over pictures**: the contrast check leaves text over a background picture alone, and Dark Reader can make such text hard to read (Amazon's banners).
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
