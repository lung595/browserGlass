pragma Singleton
import QtQuick

// Stand-in for DMS's ToastService: records every toast instead of showing it.
// log: [{level: "info" | "warning" | "error", message, details, command, category}, ...]
QtObject {
    readonly property int levelInfo: 0
    readonly property int levelWarn: 1
    readonly property int levelError: 2
    property var log: []

    function showToast(message, level, details, command, category) {
        const lv = level === undefined ? levelInfo : level;
        log = log.concat([{
                "level": lv === levelError ? "error" : (lv === levelWarn ? "warning" : "info"),
                "message": message,
                "details": details === undefined ? "" : details,
                "command": command === undefined ? "" : command,
                "category": category === undefined ? "" : category
            }]);
    }
    function showInfo(message, details, command, category) {
        showToast(message, levelInfo, details, command, category);
    }
    function showWarning(message, details, command, category) {
        showToast(message, levelWarn, details, command, category);
    }
    function showError(message, details, command, category) {
        showToast(message, levelError, details, command, category);
    }
    function dismissCategory(category) {
    }
    function hideToast() {
    }
    // The toasts of one level ("info", "warning" or "error")
    function ofLevel(level) {
        return log.filter(t => t.level === level);
    }
    function reset() {
        log = [];
    }
}
