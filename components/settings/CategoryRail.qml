import QtQuick
import qs.Common

// The categories of the settings page, left of the content: one row each,
// the open one behind a pane of glass. 176 px wide, 48 px with icons only
// when the page is narrow. Static: no timer, no animation at rest.
Item {
    id: rail

    required property var view

    readonly property int rowHeight: 44

    width: view.compact ? 48 : 176
    height: view.categories.length * rowHeight
    Accessible.role: Accessible.PageTabList

    Column {
        width: parent.width
        Repeater {
            model: rail.view.categories
            RailEntry {
                width: rail.width
                height: rail.rowHeight
                view: rail.view
            }
        }
    }
}
