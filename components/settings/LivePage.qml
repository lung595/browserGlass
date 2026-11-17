import QtQuick
import qs.Common
import qs.Widgets
import qs.Modules.Plugins
import "../logic.js" as Logic

// Live control: the companion add-on, and where it stands.
CategoryPage {
    id: page
    category: "live"

    required property var settings

    readonly property var companion: page.settings.status && page.settings.status.companion && typeof page.settings.status.companion === "object" ? page.settings.status.companion : null

    ToggleSetting {
        objectName: "liveControl"
        visible: page.shown("liveControl")
        settingKey: "liveControl"
        label: page.label("liveControl")
        description: page.help("liveControl")
        defaultValue: true
    }

    // Where it stands, as the status block says it (read only)
    StyledText {
        objectName: "liveState"
        visible: page.companion !== null && page.shown("liveControl")
        width: parent.width
        text: page.companion ? I18n.trFor("browserGlass", Logic.liveStatusText(String(page.companion.state || ""))) : ""
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
    }
}
