# v0 reference scripts

`browser-glass-sync` (bash, needs jq and awk) and `browser-glass-sites`
(Python) are the **unmodified** scripts of browserGlass v0, kept byte for byte
as a historical fixture. Their comments and messages are in French, as they
were shipped.

They are never run by the plugin. `tests/py/test_roundtrip_v0.py` runs them
inside a throwaway fake HOME to seed a real v0 install, then checks that v1
`sync` migrates it without duplicates and that v1 `uninstall` brings the tree
back to its state before v0, byte for byte.

Do not edit them: the test pins their SHA-256. Being verbatim historical
fixtures, they are the one exception to the rule that code and comments are
in English.

| File | SHA-256 |
|---|---|
| `browser-glass-sync` | `23b20505f17aad0a25030957000024623e901dc49fee3ce3a665b95e011b68ce` |
| `browser-glass-sites` | `4042fa45a91361e64a4726498dfaa42f248da038cdbd8565776538ea8630e9c7` |

Known v0 behaviour the test accounts for: v0 writes through a temporary file
and `mv`, so it replaces a symlinked `user.js` with a regular file holding the
same text (the link target itself is left untouched). v1 cannot know a link
was there, so after a v0 install the round trip ends with that regular file.
