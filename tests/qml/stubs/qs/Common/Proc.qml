pragma Singleton
import QtQuick
import Quickshell.Io

// Stand-in for DMS's Proc: nothing is ever run. Same API and the same
// debounce as the real one (requests with the same id within debounceMs
// collapse into one launch, carrying the last command and callback), but a
// launch records the command and answers with a canned result.
//
// What a test reads:
//   calls     every runCommand() request: {id, command, debounceMs, timeoutMs}
//   launched  every launch after the debounce (what would really have run):
//             {id, command, output, exitCode, settingsFile}
//             settingsFile: for a command with `--settings-file FILE`, what
//             FILE held in FileViewLog at launch (null: missing); the launch
//             then deletes it, as `browserglass.py sync` does
//   released  every release(id)
// What a test sets:
//   results   id -> {output, exitCode}, or a function(command, id) returning one
//   defaultResult  the answer for an id without one ({output: "", exitCode: 0})
//   autoRun   true: launches happen on their debounce timer, like DMS; false:
//             nothing launches until the test calls flush()
// Helpers: setResult(), flush(), isPending(), commandsFor(), lastCommand(), reset().
//
// `owner` works as in DMS: when the owner object has been destroyed by launch
// time, nothing runs (the entry is released, recorded in `released`) and the
// callback is never called.
QtObject {
    id: proc

    readonly property int noTimeout: -1
    readonly property string dmsBin: "dms"
    property int defaultDebounceMs: 50
    property int defaultTimeoutMs: 10000

    property bool autoRun: true
    property var calls: []
    property var launched: []
    property var released: []
    property var results: ({})
    property var defaultResult: ({
            "output": "",
            "exitCode": 0
        })

    // id -> {command, callback, waitMs, due, seq, timer}
    property var _pending: ({})
    property int _seq: 0
    property Component _timerComponent: Component {
        Timer {
            repeat: false
        }
    }

    function runCommand(id, command, callback, debounceMs, timeoutMs, owner) {
        const wait = (typeof debounceMs === "number" && debounceMs >= 0) ? debounceMs : defaultDebounceMs;
        const timeout = (typeof timeoutMs === "number") ? timeoutMs : defaultTimeoutMs;
        const procId = id ? id : "random-" + (++_seq);
        calls = calls.concat([{
                "id": procId,
                "command": command,
                "debounceMs": wait,
                "timeoutMs": timeout
            }]);
        let entry = _pending[procId];
        if (!entry) {
            entry = {
                "timer": null
            };
            _pending[procId] = entry;
        }
        entry.command = command;
        entry.callback = callback;
        entry.owner = owner;
        entry.waitMs = wait;
        entry.due = Date.now() + wait;
        entry.seq = ++_seq;
        if (autoRun) {
            if (!entry.timer) {
                entry.timer = _timerComponent.createObject(proc);
                entry.timer.triggered.connect(() => proc._launch(procId));
            }
            entry.timer.interval = wait;
            entry.timer.restart();
        }
    }

    function release(id) {
        if (!id)
            return;
        released = released.concat([id]);
        _drop(id);
    }

    // Launches every request pending now, soonest first; returns how many.
    // Requests the callbacks make meanwhile wait for the next flush().
    function flush() {
        const ids = Object.keys(_pending).sort((a, b) => (_pending[a].due - _pending[b].due) || (_pending[a].seq - _pending[b].seq));
        for (const id of ids)
            _launch(id);
        return ids.length;
    }

    function setResult(id, output, exitCode) {
        const next = Object.assign({}, results);
        next[id] = {
            "output": output === undefined ? "" : output,
            "exitCode": exitCode === undefined ? 0 : exitCode
        };
        results = next;
    }
    function isPending(id) {
        return _pending[id] !== undefined;
    }
    function pendingIds() {
        return Object.keys(_pending);
    }
    // The commands launched under `id`, oldest first
    function commandsFor(id) {
        return launched.filter(l => l.id === id).map(l => l.command);
    }
    function lastCommand(id) {
        const list = commandsFor(id);
        return list.length ? list[list.length - 1] : null;
    }
    function reset() {
        for (const id of Object.keys(_pending))
            _drop(id);
        calls = [];
        launched = [];
        released = [];
        results = {};
        defaultResult = {
            "output": "",
            "exitCode": 0
        };
        autoRun = true;
    }

    function _drop(id) {
        const entry = _pending[id];
        if (!entry)
            return;
        if (entry.timer) {
            entry.timer.stop();
            entry.timer.destroy();
        }
        delete _pending[id];
    }

    function _answer(id, command) {
        let r = results[id];
        if (typeof r === "function")
            r = r(command, id);
        if (r === undefined || r === null)
            r = defaultResult;
        return {
            "output": r.output === undefined ? "" : String(r.output),
            "exitCode": r.exitCode === undefined ? 0 : r.exitCode
        };
    }

    // A destroyed QObject wrapper stays truthy; Qt.isQtObject tells (as DMS)
    function _ownerDead(entry) {
        return entry.owner && !Qt.isQtObject(entry.owner);
    }

    function _launch(id) {
        const entry = _pending[id];
        if (!entry)
            return;
        if (_ownerDead(entry)) {
            release(id);
            return;
        }
        const command = entry.command;
        const callback = entry.callback;
        _drop(id);
        let settingsFile;
        const at = Array.isArray(command) ? command.indexOf("--settings-file") : -1;
        if (at >= 0) {
            const file = command[at + 1];
            settingsFile = FileViewLog.has(file) ? FileViewLog.read(file) : null;
            FileViewLog.remove(file);
        }
        const r = _answer(id, command);
        launched = launched.concat([{
                "id": id,
                "command": command,
                "output": r.output,
                "exitCode": r.exitCode,
                "settingsFile": settingsFile
            }]);
        if (typeof callback === "function") {
            try {
                callback(r.output, r.exitCode);
            } catch (e) {
                // A warning fails the run, as an error in a real callback should
                console.warn("Proc stub: callback error for", id, ":", e);
            }
        }
    }
}
