pragma Singleton
import QtQuick

// The Process stand-ins that exist right now, and a record of every launch
// that outlives the Process object (a plugin may start one while it is being
// destroyed).
//
//   live      every Process object made; alive() keeps those that still
//             exist. (QML raises Component.onDestruction when an object's
//             creation context dies, even if the object lives on, e.g. a
//             Process created by a plugin being unloaded and parented
//             elsewhere: so liveness is checked with Qt.isQtObject.)
//   runs      one entry per launch, oldest first:
//             {command: [argv...], stdin: "text written to stdin",
//              stdinClosed: bool, detached: bool, exited: null | exit code}
//             `running: true` and exec() launch with stdin (when
//             stdinEnabled); startDetached() launches without it.
//   dropped   what was written while no process ran or stdin was off (the
//             real Process drops it too): [[argv..., text], ...]
QtObject {
    id: log

    property var live: []
    property var runs: []
    property var dropped: []

    // Raises `started` on the next turn, if that process still runs then
    property var _toAnnounce: []
    property Timer _announcer: Timer {
        interval: 0
        repeat: false
        onTriggered: {
            const list = log._toAnnounce;
            log._toAnnounce = [];
            for (const p of list) {
                if (Qt.isQtObject(p) && p.running)
                    p.started();
            }
        }
    }
    function announce(process) {
        _toAnnounce = _toAnnounce.concat([process]);
        _announcer.restart();
    }

    function born(process) {
        live = live.concat([process]);
    }
    function died(process) {
        live = live.filter(p => p !== process && Qt.isQtObject(p));
    }
    function alive() {
        return live.filter(p => Qt.isQtObject(p));
    }

    // Returns the index of the new run
    function launch(command, detached) {
        runs = runs.concat([{
                "command": command ? Array.from(command).map(String) : [],
                "stdin": "",
                "stdinClosed": false,
                "detached": !!detached,
                "exited": null
            }]);
        return runs.length - 1;
    }
    function update(index, fields) {
        if (index < 0 || index >= runs.length)
            return;
        const next = runs.slice();
        next[index] = Object.assign({}, next[index], fields);
        runs = next;
    }
    function drop(command, text) {
        dropped = dropped.concat([[Array.from(command || []).map(String), String(text)]]);
    }
    function commands() {
        return runs.map(r => r.command);
    }
    function last() {
        return runs.length ? runs[runs.length - 1] : null;
    }
    function reset() {
        runs = [];
        dropped = [];
    }
}
