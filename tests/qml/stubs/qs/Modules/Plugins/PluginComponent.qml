import QtQuick
import qs.Common

// Stand-in for DMS's PluginComponent (daemon and bar widget root). The plugin
// data loading is the real one: once pluginId and pluginService are set,
// pluginData is SettingsData's copy for the plugin, reloaded on
// pluginDataChanged. Nothing is shown: a widget test builds a pill itself
// (widget.horizontalBarPill.createObject(parentItem)) and reads _testPopoutOpen (test-only, so the _test prefix),
// which triggerPopout() toggles and closePopout() clears.
Item {
    id: root

    property string pluginId: ""
    property var pluginService: null
    property var pluginData: ({})
    property var variants: []

    property var surfaceContext: null
    property string widgetInstanceId: ""
    readonly property string popoutTriggerId: widgetInstanceId || pluginId
    property var axis: null
    property string section: "center"
    property var parentScreen: null
    property real widgetThickness: 30
    property real barThickness: 48
    property real barSpacing: 4
    property var barConfig: null
    property string visibilityCommand: ""
    property int visibilityInterval: 0
    property bool conditionVisible: true

    property Component horizontalBarPill: null
    property Component verticalBarPill: null
    property Component popoutContent: null
    property real popoutWidth: 400
    property real popoutHeight: 0
    property var pillClickAction: null
    property var pillRightClickAction: null

    property Component controlCenterWidget: null
    property string ccWidgetIcon: ""
    property string ccWidgetPrimaryText: ""
    property string ccWidgetSecondaryText: ""
    property bool ccWidgetIsActive: false
    property bool ccWidgetIsToggle: true
    property Component ccDetailContent: null
    property real ccDetailHeight: 250
    signal ccWidgetToggled
    signal ccWidgetExpanded

    readonly property bool isVertical: axis?.isVertical ?? false
    readonly property bool hasHorizontalPill: horizontalBarPill !== null
    readonly property bool hasVerticalPill: verticalBarPill !== null
    readonly property bool hasPopout: popoutContent !== null
    readonly property int iconSize: Theme.barIconSize(barThickness, -4)
    readonly property int iconSizeLarge: Theme.barIconSize(barThickness)
    readonly property int textSize: Theme.barTextSize(barThickness)

    // Test-only: the popout state, and how often it was asked for
    property bool _testPopoutOpen: false
    property int _testPopoutRequests: 0

    onPluginServiceChanged: loadPluginData()
    onPluginIdChanged: loadPluginData()

    Connections {
        target: root.pluginService
        function onPluginDataChanged(changedPluginId) {
            if (changedPluginId === root.pluginId)
                root.loadPluginData();
        }
    }

    function loadPluginData() {
        if (!pluginService || !pluginId) {
            pluginData = {};
            variants = [];
            return;
        }
        pluginData = SettingsData.getPluginSettingsForPlugin(pluginId);
        variants = pluginService.getPluginVariants(pluginId);
    }
    function triggerPopout() {
        if (pillClickAction) {
            pillClickAction();
            return;
        }
        if (!hasPopout)
            return;
        _testPopoutRequests++;
        _testPopoutOpen = !_testPopoutOpen;
    }
    function closePopout() {
        _testPopoutOpen = false;
    }
    function setVisibilityOverride(visible) {
        conditionVisible = visible;
    }
    function clearVisibilityOverride() {
        conditionVisible = true;
    }
}
