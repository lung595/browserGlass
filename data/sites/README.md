# Site fixes

One plain CSS file per website, written for Browser Glass. This is the place to
fix or improve how a site looks under the glass.

- **Name the file after the site**: `youtube.com.css` applies to youtube.com and
  its subdomains. If [my-internet](https://github.com/sameerasw/my-internet) has
  a style with that name, the file is added at the end of that style. If it has
  none, the file becomes a new style of its own.
- **Use the glass tint** for anything that floats over the page (fixed headers,
  toolbars, overlay menus): `background: var(--browserglass-bar)` is the DMS
  surface at 80 %, light or dark like the browser. Add a
  `backdrop-filter: blur(24px)` behind it.
- **Write plain CSS** with `!important`. No `@import`, no `url()` and no
  `@-moz-document`: the tests (`tests/py/test_sites.py`) refuse them.
- **Begin with a comment** that says what the file fixes.
- **No fix is needed for a light-only site** whose dark text is unreadable on
  the dark tint: under a dark theme, a site style applies only to pages that
  declare a dark version, and with the companion add-on the tint follows the
  page's own tone (see "Light pages under a dark theme" in
  [the user guide](../../docs/GUIDE.md#light-pages-under-a-dark-theme)).

Everything else in `data/` is copied from my-internet by a weekly job: do not
edit `styles.json` or `css-mapping.json`; send those changes upstream.
