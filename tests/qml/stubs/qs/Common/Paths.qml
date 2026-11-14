pragma Singleton
import QtQuick

// DMS's paths, under the made-up home of the Quickshell stand-in
QtObject {
    readonly property url home: "file:///tmp/fakehome"
    readonly property url xdgCache: "file:///tmp/fakehome/.cache"
    readonly property url data: "file:///tmp/fakehome/.local/share/dms"
    readonly property url state: "file:///tmp/fakehome/.local/state/dms"
    readonly property url cache: "file:///tmp/fakehome/.cache/dms"
    readonly property url config: "file:///tmp/fakehome/.config/dms"

    function expandTilde(p) {
        return String(p).replace(/^~(?=\/|$)/, "/tmp/fakehome");
    }
    // Same as DMS: decode, drop the scheme
    function strip(u) {
        return decodeURIComponent(String(u)).replace("file://", "");
    }
}
