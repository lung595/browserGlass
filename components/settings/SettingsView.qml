import QtQuick
import "SettingsSearch.js" as Search
import "SettingsView.js" as View

// The state of the settings page: which category is open, what is typed in
// the search field and what it matches. Pure bindings, no timer: the page
// does nothing until someone types or clicks.
QtObject {
    id: view

    property SettingsIndex index: SettingsIndex {}
    readonly property var categories: index.categories
    // Opens on the status: what most people come to the page for
    property string current: "status"
    property string query: ""
    // A narrow page (the plugin settings of a small window): icons only
    property bool compact: false
    // The rows the page hides right now ({id: true}), set by the page: a
    // search that finds one shows its anchor instead, or nothing
    property var hidden: ({})
    // The row a search just opened, to light it. The counter moves on every
    // opening so that opening the same row twice lights it twice.
    property string litKey: ""
    property int litCount: 0

    readonly property var _entries: View.byId(index.entries)
    // Folded once per language, not on every key
    readonly property var _prepared: Search.prepare(index.entries)

    readonly property bool filtering: query.trim() !== ""
    // Searching the 30-odd entries takes well under a millisecond: nothing is kept
    readonly property var found: View.group(filtering ? Search.search(_prepared, query) : [], _entries, hidden)
    readonly property var hits: found.ids
    readonly property var counts: found.counts
    readonly property var firsts: found.firsts
    readonly property bool hasResults: found.first !== null

    // The label and the help line of a row, as the index words them
    function label(key) {
        return _entries[key] ? _entries[key].label : "";
    }

    function help(key) {
        return _entries[key] ? _entries[key].help : "";
    }

    function info(id) {
        return View.find(categories, id);
    }

    // Leaves the search and opens a category, optionally lighting one of its rows
    function open(category, key) {
        query = "";
        current = category;
        if (key) {
            litKey = key;
            litCount++;
        }
    }

    // A click on a category of the rail: while searching, it opens at the
    // best match it holds, otherwise it just opens
    function pick(category) {
        open(category, filtering ? (firsts[category] || "") : "");
    }

    // Enter in the search field: opens the best match and lights it
    function openFirst() {
        if (found.first)
            open(found.first.category, found.first.id);
    }
}
