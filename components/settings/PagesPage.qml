import QtQuick
import qs.Common
import qs.Widgets
import qs.Modules.Plugins

// Which pages are glass, and whether they are asked for light or dark.
CategoryPage {
    id: page
    category: "pages"

    SelectionSetting {
        objectName: "siteTheme"
        visible: page.shown("siteTheme")
        settingKey: "siteTheme"
        label: page.label("siteTheme")
        description: page.help("siteTheme")
        options: [
            {
                "label": I18n.trFor("browserGlass", "Follow DMS"),
                "value": "follow"
            },
            {
                "label": I18n.trFor("browserGlass", "Always dark"),
                "value": "dark"
            },
            {
                "label": I18n.trFor("browserGlass", "Leave as is"),
                "value": "none"
            }
        ]
        defaultValue: "follow"
    }

    // The browser follows the system light/dark scheme live; DMS writes its
    // mode there only with "Sync with portal" on.
    StyledText {
        objectName: "portalHint"
        visible: !SettingsData.syncModeWithPortal && page.shown("portalHint")
        width: parent.width
        text: page.label("portalHint")
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.warning
    }

    ToggleSetting {
        objectName: "darkPages"
        visible: page.shown("darkPages")
        settingKey: "darkPages"
        label: page.label("darkPages")
        description: page.help("darkPages")
        defaultValue: true
    }

    ToggleSetting {
        objectName: "pagesTransparent"
        visible: page.shown("pagesTransparent")
        settingKey: "pagesTransparent"
        label: page.label("pagesTransparent")
        description: page.help("pagesTransparent")
        defaultValue: true
    }

    ToggleSetting {
        objectName: "newTabGlass"
        visible: page.shown("newTabGlass")
        settingKey: "newTabGlass"
        label: page.label("newTabGlass")
        description: page.help("newTabGlass")
        defaultValue: true
    }

    ToggleSetting {
        objectName: "readerOpaque"
        visible: page.shown("readerOpaque")
        settingKey: "readerOpaque"
        label: page.label("readerOpaque")
        description: page.help("readerOpaque")
        defaultValue: true
    }

    ToggleSetting {
        objectName: "privateGlass"
        visible: page.shown("privateGlass")
        settingKey: "privateGlass"
        label: page.label("privateGlass")
        description: page.help("privateGlass")
        defaultValue: true
    }
}
