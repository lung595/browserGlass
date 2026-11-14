pragma Singleton
import QtQuick

// Stand-in for Quickshell's global: a made-up environment (no real path, no
// real account) and a record of every detached command instead of running it.
QtObject {
    property var screens: ["screen0"]
    property string shellDir: "/tmp/fakehome/.config/quickshell"
    // What Quickshell.env() answers; a test may replace it
    property var environment: ({
            "HOME": "/tmp/fakehome",
            "USER": "alice"
        })
    // Every execDetached(argv), in order: [[argv...], ...]
    property var detached: []

    function env(name) {
        const value = environment[name];
        return value === undefined ? null : value;
    }
    function execDetached(command) {
        detached = detached.concat([command]);
    }
    function reset() {
        detached = [];
    }
}
