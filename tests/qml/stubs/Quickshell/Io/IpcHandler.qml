import QtQuick

// Stand-in for Quickshell's IpcHandler: the functions declared on it are the
// commands. It registers with IpcRegistry so a test can play
// `dms ipc call <target> <function> args...` with IpcRegistry.call().
QtObject {
    id: handler

    property string target: ""
    property bool enabled: true

    Component.onCompleted: IpcRegistry.register(handler)
    Component.onDestruction: IpcRegistry.unregister(handler)
}
