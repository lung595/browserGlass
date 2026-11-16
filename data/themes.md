# Site theme recipes (`themes.json`)

Under a dark theme, with *Live control* and *Dark pages* on, the companion
add-on (`extension/theme.js`) writes the value a site reads to pick its own
theme, before the page's scripts run, and puts the prior value back
afterwards. This file says what to write. The helper reads it
(`themes_load()` in `browserglass.py`), drops what is not valid
(`themes_clean()`), and sends the rest to the add-on with every list.

```json
{
  "generic": {
    "keys": ["appearance", "color-mode", "color-scheme", "colorMode", "colorScheme", "theme"],
    "map": {"light": "dark", "Light": "Dark", "LIGHT": "DARK", "\"light\"": "\"dark\""}
  },
  "sites": {
    "example.org": [
      {"store": "local", "key": "theme", "op": "set", "from": ["light", null], "to": "dark",
       "verified": "2026-11-15", "note": "the theme menu writes localStorage.theme"}
    ]
  }
}
```

## The generic rule

For a site with no recipe: each key of `keys` that already exists in the
page's `localStorage` with a value of `map` gets the paired value. Never a
cookie, never a key created. `"light"` with its quotes covers sites that
store JSON strings.

## Recipes

`sites` maps a host to its recipes (sorted by host; a recipe for
`example.org` also covers `www.example.org`; the closest host wins, and a
host with recipes skips the generic rule). Each recipe:

| Field | |
|---|---|
| `store` | `local` (the page's `localStorage`) or `cookie`. |
| `key` | The key or cookie name (letters, digits, `_ . : -`, at most 64; a `localStorage` key may also hold `/`). |
| `op` | `set`: a value of `from` becomes `to`. `swap`: the substring `from[0]` of a composite value (`"…-day-…"`) becomes `to`. |
| `from` | The values meaning light. `null` stands for "absent" (`set` only): the key is then created. Never `to` itself. `swap` takes exactly one non-empty string. |
| `to` | The dark value (at most 64 characters, no control character; a cookie value also no `;` or `,`). A `localStorage` value may be JSON: `"{\"theme\":\"default\"}"`. |
| `path`, `domain` | Cookies only. `path` starts with `/` (default `/`); `domain`, when given, is the host or a parent of it (no `domain`: a host-only cookie). |
| `reload` | Cookies only, `true` when the server draws the theme from the cookie: the page is reloaded once, at `document_start`, after the first write. |
| `skipIfCookie` | A cookie whose presence means a signed-in account (whose theme comes from the server): no write. |
| `verified` | The date (`YYYY-MM-DD`) the recipe was last checked on the real site. |
| `note` | What the site does, in a few words. |

`verified` and `note` are required and stay here: they are not sent. Any
row that breaks a rule is dropped alone. `rev`, a hash of what is sent, is
added by the helper: a page where a write failed is tried again only once
`rev` changes.

## Verifying a recipe

1. Open the site in a fresh private window, signed out, and note its theme
   storage: the devtools *Storage* panel, before and after choosing *Dark*
   in its theme menu (only the key that changes matters).
2. Check that the dark value alone, set before load, gives the dark theme:
   in a fresh window, set it from the console on the site, then reload.
   For a cookie, check whether the first response is already dark (then the
   server draws it, and the recipe needs `reload`).
   A cookie the site sets `HttpOnly` cannot be seen or replaced by the
   add-on: when a visitor already has one, the write is refused and the
   page reloads once; a page still light is then marked failed (Dark
   Reader takes over).
   A site that keeps the theme in two places needs a recipe only for the
   one it reads at start: Excalidraw stores `excalidraw-theme` and a
   `theme` inside its `excalidraw-state` JSON, reads only the first
   (light when absent, even with `"theme":"dark"` in the second) and
   writes both back, so one `localStorage` recipe, no reload, covers it.
   A value stored as JSON is written whole, as a string: the Home
   Assistant demo reads `demo_theme` as `{"theme":"default","dark":false}`
   when absent; `{"theme":"default"}` (no `dark` key, its Auto theme)
   gives its dark theme under a dark system and follows the system live.
   The recipe lists `null` and the light JSON in `from`, exactly as the
   site writes it (key order and spacing included).
   A value need not say light or dark: Proton's account pages keep
   `theme` as a number (`2` light, `1` dark, `0` Auto, which follows the
   system live; absent, light even under a dark system), so the recipe
   writes `1` over `null` and `2`, and leaves `0` alone.
3. Check that the light value (or none) gives the light theme, so that
   putting it back restores the site.
   A site that stores its own default on a first visit (the French
   state's DSFR stores `scheme` = `light`) needs both `null` and that
   value in `from`; a value that already follows the system (`system`)
   stays out of it. A site that stores the scheme it resolved from the
   system (DSFR on impots.gouv.fr: `light` or `dark`, never `system`)
   stays dark under a light theme after a visit under a dark one; a
   recipe makes the key the add-on's, so the value it had is put back.
4. Write the recipe with today's date in `verified`, and run
   `python3 -m unittest tests/py/test_themes.py`.

Never sign in, type credentials or submit a form to verify a recipe: a
recipe is for what a visitor sees.
