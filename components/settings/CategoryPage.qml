import QtQuick
import qs.Common
import qs.Widgets
import qs.DCommon.Widgets

// One category of the settings: its title, then its rows as children. A
// page shows only while its category is open, or, during a search, only if
// it has a match; inside it a row shows if it matches (see shown()).
Item {
    id: page

    required property var view
    required property string category
    // The rows of the category go in the column, under the title
    default property alias content: column.data

    readonly property var info: view.info(category) || ({})
    readonly property bool reduceMotion: SettingsData.reduceMotion

    // Whether the row `key` shows: always while browsing (the page itself is
    // shown or hidden), only the matches (and their anchors) while a search
    // filters
    function shown(key) {
        return !view.filtering || view.hits[key] === true;
    }

    function label(key) {
        return view.label(key);
    }

    function help(key) {
        return view.help(key);
    }

    // The row called `key` (its objectName) among the children, looking everywhere below
    function _find(item, key) {
        for (const child of item.children) {
            if (child.objectName === key)
                return child;
            const inside = _find(child, key);
            if (inside)
                return inside;
        }
        return null;
    }

    // The settings page's scroll (DMS's PluginSettings.ensureItemVisible), when there is one
    function _reveal(target) {
        for (let item = page.parent; item; item = item.parent) {
            if (typeof item.ensureItemVisible === "function") {
                item.ensureItemVisible(target);
                return;
            }
        }
    }

    // Frames the row `key` for a moment: full, held, then one fade. With
    // Reduce motion it stays lit until the next click on the page.
    function light(key) {
        const target = _find(column, key);
        if (!target)
            return;
        frame.row = target;
        _place();
        fade.stop();
        frame.opacity = 1;
        if (!reduceMotion)
            fade.start();
        _reveal(target);
    }

    // The frame sits over the page, around the row: never inside it, where a
    // Column (some setting widgets are one) would lay it out as a line
    function _place() {
        const row = frame.row;
        if (!row)
            return;
        const at = row.mapToItem(page, 0, 0);
        frame.x = at.x - Theme.spacingXS;
        frame.y = at.y - Theme.spacingXS;
        frame.width = row.width + Theme.spacingXS * 2;
        frame.height = row.height + Theme.spacingXS * 2;
    }
    onWidthChanged: _place()

    objectName: "page:" + category
    visible: view.filtering ? (view.counts[category] || 0) > 0 : view.current === category
    width: parent ? parent.width : 0
    implicitHeight: column.implicitHeight

    // Brief fade in when the page appears (100 ms for a filter, 150 ms for a category)
    onVisibleChanged: {
        if (!visible || reduceMotion)
            return;
        enter.duration = view.filtering ? 100 : 150;
        enter.restart();
    }
    NumberAnimation {
        id: enter
        target: column
        property: "opacity"
        from: 0
        to: 1
        easing.type: Easing.OutCubic
    }

    Connections {
        target: page.view
        function onLitCountChanged() {
            // After the page is shown and laid out
            if (page.view.current === page.category)
                Qt.callLater(page.light, page.view.litKey);
        }
    }

    TapHandler {
        // Only matters to a lit frame that Reduce motion keeps; passive: the rows still get their clicks
        enabled: frame.opacity > 0 && page.reduceMotion
        gesturePolicy: TapHandler.ReleaseWithinBounds
        grabPermissions: PointerHandler.ApprovesTakeOverByAnything
        onTapped: frame.opacity = 0
    }

    Rectangle {
        id: frame
        objectName: "litFrame"
        // The row it frames; it follows the row while the layout settles
        property Item row: null
        // Over the rows: a faint tint and an outline, it takes no click
        z: 1
        opacity: 0
        visible: opacity > 0
        radius: Theme.cornerRadius / 2
        color: Theme.withAlpha(Theme.primary, 0.08)
        border.width: 1
        border.color: Theme.primary

        Connections {
            target: frame.row
            enabled: frame.visible
            function onYChanged() {
                page._place();
            }
            function onHeightChanged() {
                page._place();
            }
            function onWidthChanged() {
                page._place();
            }
        }
    }
    SequentialAnimation {
        id: fade
        PauseAnimation {
            duration: 300
        }
        NumberAnimation {
            target: frame
            property: "opacity"
            to: 0
            duration: 300
            easing.type: Easing.OutCubic
        }
    }

    Column {
        id: column
        width: parent.width
        spacing: Theme.spacingM

        Row {
            width: parent.width
            spacing: Theme.spacingS
            height: 28
            DIcon {
                id: titleIcon
                anchors.verticalCenter: parent.verticalCenter
                name: page.info.icon || ""
                size: 20
                color: Theme.primary
            }
            StyledText {
                id: titleText
                objectName: "pageTitle"
                anchors.verticalCenter: parent.verticalCenter
                text: page.info.name || ""
                wrapMode: Text.NoWrap
                font.pixelSize: Theme.fontSizeLarge
                font.weight: Font.Bold
                color: Theme.surfaceText
            }
            StyledText {
                objectName: "pageHelp"
                anchors.verticalCenter: parent.verticalCenter
                visible: !page.view.compact
                width: Math.max(0, parent.width - titleIcon.width - titleText.width - parent.spacing * 2)
                text: "· " + (page.info.help || "")
                wrapMode: Text.NoWrap
                elide: Text.ElideRight
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.surfaceVariantText
            }
        }
    }
}
