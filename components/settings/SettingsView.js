.pragma library

// What the settings page needs to know about a search, as plain data: which
// rows show, how many matched per category, and the first match (the one
// Enter opens). Pure, so the page only binds to it and the test can read it.

// Index entries by id, to read a row's label, help, category and anchor
function byId(entries) {
    const map = {};
    for (const e of Array.isArray(entries) ? entries : [])
        map[e.id] = e;
    return map;
}

// `results` come from SettingsSearch.search(), best first; `entries` is the
// map made by byId(). `hidden` names the rows the page does not show right
// now (the opacity slider while the override is off...): a hidden match shows
// its `anchor` instead (the override switch), or nothing. A row shown also
// shows its anchor, so a setting never appears without the one it depends
// on; only the rows found are counted. `firsts` names the best-ranked match
// of each category, `first` the best one.
function group(results, entries, hidden) {
    const out = { "ids": {}, "counts": {}, "firsts": {}, "first": null };
    const off = hidden || {};
    for (const r of Array.isArray(results) ? results : []) {
        let entry = entries[r.id];
        if (entry && off[entry.id])
            entry = entry.anchor ? entries[entry.anchor] : null;
        if (!entry || off[entry.id] || out.ids[entry.id])
            continue;
        out.ids[entry.id] = true;
        out.counts[entry.category] = (out.counts[entry.category] || 0) + 1;
        if (!out.firsts[entry.category])
            out.firsts[entry.category] = entry.id;
        if (out.first === null)
            out.first = { "id": entry.id, "category": entry.category };
    }
    for (const id of Object.keys(out.ids)) {
        const anchor = entries[id].anchor;
        if (anchor && !off[anchor])
            out.ids[anchor] = true;
    }
    return out;
}

// The category entry for `id` (or null)
function find(list, id) {
    return list.find(c => c.id === id) || null;
}
