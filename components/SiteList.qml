import QtQuick
import qs.Common
import qs.Widgets
import qs.DCommon.Widgets

// The dedicated site styles (`sites --json`, cached by the daemon) with a
// search field and one switch each. A switched-off style's name goes to the
// `settingKey` list (disabledStyles). Loads and saves through the settings
// page like DMS's setting widgets: the nearest ancestor with
// loadValue/saveValue, and loadValue() again when the page reloads its
// children. The list is a ListView over the filtered sites, so only the
// visible rows exist (not ~660 delegates).
Column {
    id: list

    property string settingKey: "disabledStyles"
    // [{name, domains}], or null while the daemon has not loaded them
    property var sites: null
    property real listHeight: 320
    // Names of the switched-off styles
    property var disabled: []
    property alias query: search.text
    // The title and the line under it (the settings page reads them from its index)
    property string label: I18n.trFor("browserGlass", "Dedicated site styles")
    property string description: I18n.trFor("browserGlass", "Styles from my-internet that make known sites glass-friendly. Switch one off and that site keeps only the plain see-through page background: the generic style does not take its place.")

    readonly property var filtered: filterSites(sites, query)
    readonly property int total: Array.isArray(sites) ? sites.length : 0
    readonly property int disabledCount: countDisabled(sites, disabled)

    width: parent ? parent.width : 0
    spacing: Theme.spacingS

    // What a style is called on screen: its file name without the + or -
    // prefix (+x.com: x.com and its subdomains; -x.com: x.com on any TLD)
    function displayName(name) {
        return String(name || "").replace(/^[+-]/, "");
    }

    // The sites whose name or one of whose domains contains every word of
    // `text` (case-insensitive), in their order
    function filterSites(all, text) {
        if (!Array.isArray(all))
            return [];
        const words = String(text || "").toLowerCase().split(/\s+/).filter(w => w !== "");
        if (words.length === 0)
            return all;
        return all.filter(site => {
            const hay = [String(site.name || "")].concat(Array.isArray(site.domains) ? site.domains : []).join(" ").toLowerCase();
            return words.every(w => hay.indexOf(w) >= 0);
        });
    }

    function countDisabled(all, names) {
        if (!Array.isArray(all) || !Array.isArray(names) || names.length === 0)
            return 0;
        return all.filter(site => names.indexOf(site.name) >= 0).length;
    }

    function isEnabled(name) {
        return list.disabled.indexOf(name) < 0;
    }

    function _settings() {
        let item = list.parent;
        while (item) {
            if (item.saveValue !== undefined && item.loadValue !== undefined)
                return item;
            item = item.parent;
        }
        return null;
    }

    // Strings or {name} objects (logic.js accepts both); kept as names
    function _names(value) {
        if (!Array.isArray(value))
            return [];
        const out = [];
        for (let i = 0; i < value.length; i++) {
            const v = value[i];
            const name = v !== null && typeof v === "object" ? v.name : v;
            if (typeof name === "string" && name !== "" && out.indexOf(name) < 0)
                out.push(name);
        }
        return out;
    }

    function loadValue() {
        const settings = list._settings();
        if (settings)
            list.disabled = list._names(settings.loadValue(list.settingKey, []));
    }

    // Switches one style on or off and saves the new list
    function setEnabled(name, enabled) {
        if (list.isEnabled(name) === enabled)
            return;
        const next = enabled ? list.disabled.filter(n => n !== name) : list.disabled.concat([name]);
        list.disabled = next;
        const settings = list._settings();
        if (settings)
            settings.saveValue(list.settingKey, next);
    }

    Component.onCompleted: loadValue()

    StyledText {
        width: parent.width
        text: list.label
        font.pixelSize: Theme.fontSizeLarge
        font.weight: Theme.fontWeightMedium
        color: Theme.surfaceText
    }

    StyledText {
        width: parent.width
        text: list.description
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
        wrapMode: Text.WordWrap
    }

    DTextField {
        id: search
        objectName: "siteSearch"
        width: parent.width
        placeholderText: I18n.trFor("browserGlass", "Search sites")
        leftIconName: "search"
        showClearButton: true
    }

    StyledText {
        objectName: "siteCount"
        width: parent.width
        text: list.sites === null ? I18n.trFor("browserGlass", "Loading the site styles…") : I18n.trFor("browserGlass", "%1 of %2 styles shown, %3 switched off").arg(list.filtered.length).arg(list.total).arg(list.disabledCount)
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
    }

    Rectangle {
        width: parent.width
        height: list.listHeight
        radius: Theme.cornerRadius
        color: Theme.surfaceContainerHigh
        clip: true

        ListView {
            id: view
            objectName: "siteView"
            anchors.fill: parent
            anchors.margins: Theme.spacingXS
            clip: true
            model: list.filtered
            boundsBehavior: Flickable.StopAtBounds

            delegate: Item {
                id: row
                required property var modelData
                required property int index
                width: ListView.view ? ListView.view.width : 0
                height: 48

                Column {
                    anchors.left: parent.left
                    anchors.leftMargin: Theme.spacingS
                    anchors.right: toggle.left
                    anchors.rightMargin: Theme.spacingS
                    anchors.verticalCenter: parent.verticalCenter

                    StyledText {
                        width: parent.width
                        text: list.displayName(row.modelData.name)
                        font.pixelSize: Theme.fontSizeMedium
                        color: Theme.surfaceText
                        wrapMode: Text.NoWrap
                    }
                    StyledText {
                        width: parent.width
                        text: (row.modelData.domains || []).join(", ")
                        font.pixelSize: Theme.fontSizeSmall
                        color: Theme.surfaceVariantText
                        wrapMode: Text.NoWrap
                    }
                }

                DToggle {
                    id: toggle
                    objectName: "siteToggle:" + row.modelData.name
                    anchors.right: parent.right
                    anchors.rightMargin: Theme.spacingS
                    anchors.verticalCenter: parent.verticalCenter
                    checked: list.isEnabled(row.modelData.name)
                    onToggled: checked => list.setEnabled(row.modelData.name, checked)
                }
            }
        }

        StyledText {
            objectName: "siteEmpty"
            anchors.centerIn: parent
            visible: list.sites !== null && list.filtered.length === 0
            text: I18n.trFor("browserGlass", "No site matches")
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.surfaceVariantText
        }
    }
}
