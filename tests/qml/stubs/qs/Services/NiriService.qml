pragma Singleton
import QtQuick

// Stand-in for DMS's NiriService: the niri windows ({id, app_id, title, pid,
// is_focused}, as niri's event stream gives them) and the last focused one,
// which a test sets.
QtObject {
    property var windows: []
    property var lastFocusedWindowId: null

    function reset() {
        windows = [];
        lastFocusedWindowId = null;
    }
}
