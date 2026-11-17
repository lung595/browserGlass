import QtQuick
import qs.Common
import qs.Widgets
import qs.DCommon.Widgets
import qs.Modules.Plugins
import ".."

// The sites: the generic style, the exclusions and the dedicated styles.
CategoryPage {
    id: page
    category: "sites"

    required property var settings

    ToggleSetting {
        objectName: "genericStyle"
        visible: page.shown("genericStyle")
        settingKey: "genericStyle"
        label: page.label("genericStyle")
        description: page.help("genericStyle")
        defaultValue: true
    }

    ListSettingWithInput {
        objectName: "excludedSites"
        visible: page.shown("excludedSites")
        settingKey: "excludedSites"
        label: page.label("excludedSites")
        description: page.help("excludedSites")
        defaultValue: []
        fields: [
            {
                "id": "domain",
                "label": I18n.trFor("browserGlass", "Domain"),
                "placeholder": "example.com",
                "width": 260,
                "required": true
            }
        ]
    }

    DButton {
        objectName: "excludeClipboard"
        visible: page.shown("excludeClipboard")
        text: page.label("excludeClipboard")
        iconName: "content_paste"
        variant: "tonal"
        enabled: page.settings.daemon !== null
        onClicked: page.settings.daemon.excludeClipboard()
    }

    SiteList {
        objectName: "siteList"
        visible: page.shown("siteList")
        label: page.label("siteList")
        description: page.help("siteList")
        settingKey: "disabledStyles"
        sites: Array.isArray(page.settings.vars.sites) ? page.settings.vars.sites : null
    }
}
