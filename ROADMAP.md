# Roadmap

These are ideas, not promises, and they have no dates. Anything that would need the network while the plugin runs, or would send data somewhere, is out of scope.

## Planned

- **Snap Firefox in the niri rule**: add the Snap app-id (`firefox_firefox`) once it is confirmed on a real Snap install. Until then, see *Known limits*.
- **Live checks on more installs**: Zen, Floorp and Waterfox, plus the Flatpak and Snap variants. Their profile folders come from the browsers' documentation and are tested on a fake home only.
- **Light mode in the end-to-end test**: reader view and PDFs are checked in dark mode only (`tests/e2e/`).
- **Choose the profiles**: an option to leave some profiles of a browser without glass.
- **The DMS plugin registry**: submit the plugin once it has had wider use.

## Not planned

- **Chromium-based browsers**: they have no `userChrome.css` or `userContent.css` to paint the window and the pages with.
- **Restarting the browser automatically**: that would close your windows and tabs. The badge and the toast say when a restart is needed, and you choose when to restart.
- **Downloading styles at run time**: the my-internet styles are bundled in `data/` and refreshed through a pull request (see [CONTRIBUTING.md](CONTRIBUTING.md#releasing-a-version)).
- **Compositors other than niri**: the glass depends on a niri window rule.

## Known limits

- **A manual restart is needed.** Firefox reads its CSS only when it starts. After any change, colours included (a new wallpaper, light or dark mode), a running browser shows the new look only after a restart. When the glass turns on, niri applies the plugin's rule at once, so a running browser stays opaque until its restart.
- **Firefox family only**: there is no Chromium support (see *Not planned*).
- **The niri rule covers the whole app-id.** It matches every window of `firefox`, `librewolf`, `zen` and the rest. A profile without glass, started with `-profile` for instance, is also shown fully opaque instead of following DMS's global opacity.
- **Zen has not been tested live.** Its profile folders and its transparency-mod warning are tested on fixtures only.
- **Flatpak and Snap**: Snap Firefox is not in the niri rule, because its app-id could not be confirmed. Snap Firefox therefore gets the CSS tint and DMS's global opacity together, and looks more transparent than intended. No Flatpak or Snap install has been tried live. A profile outside the known profile folders is not found.
- **Opacity source**: browserGlass reads the opacity of the *first* global window rule (one without `match`) in DMS's `niri/dms/windowrules.kdl`, but niri applies the *last* one. If several global rules set different opacities, the browser can differ from your other windows. Use the opacity override in *Appearance* in that case.
- **A cleaner that waits too long gives up.** When you uninstall while a browser runs, a detached cleaner waits for that browser to close before it puts the prefs back in `prefs.js`. It polls for 7 days at most. After that it leaves its job in the state folder's `pending/` directory, and the next uninstall finishes it. Until then the browser keeps the plugin's pref values.
- **An unreadable profile lock keeps the niri rule.** When a profile's `.parentlock` exists but cannot be probed (permissions or an unusual file system), the profile counts as possibly running. Turning the glass off then keeps the plugin's niri rule, and *Status* shows it as held, until the lock can be read.
- The running-browser check reads the lock with the `struct flock` layout of x86_64 and aarch64 glibc.
- After a plugin update, run `dms restart`: DMS keeps the plugin's JavaScript and component files cached, so a reload alone may still run the old code.
