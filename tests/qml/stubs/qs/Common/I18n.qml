pragma Singleton
import QtQuick

// Stand-in for DMS's I18n: the source text comes back unless a test
// registers a plugin table ({context: {term: translation}}, the shape DMS
// loads from a plugin's translations/<lang>.json), looked up as DMS does.
QtObject {
    property var pluginTranslations: ({})

    function tr(term, context) {
        return term;
    }
    function trFor(pluginId, term, context) {
        const table = pluginTranslations[pluginId];
        if (table) {
            if (context && table[context] && table[context][term])
                return table[context][term];
            if (table[term] && table[term][term])
                return table[term][term];
            for (const c in table) {
                if (table[c] && table[c][term])
                    return table[c][term];
            }
        }
        return tr(term, context);
    }
    function registerPluginTranslations(pluginId, table) {
        const next = Object.assign({}, pluginTranslations);
        next[pluginId] = table;
        pluginTranslations = next;
    }
    function unregisterPluginTranslations(pluginId) {
        const next = Object.assign({}, pluginTranslations);
        delete next[pluginId];
        pluginTranslations = next;
    }
}
