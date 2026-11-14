import QtQuick

// Stand-in for Quickshell's Process: never runs anything. Every one is listed
// in ProcessLog (ProcessLog.alive() while it exists), and every launch is recorded in
// ProcessLog.runs (argv, what was written to stdin, whether stdin was closed),
// a record that survives the Process object.
//
// Like the real one: setting `running` to true launches `command` at once (a
// write() right after it reaches the process), `started` follows on the next
// event loop turn, write() only reaches a running process whose stdinEnabled
// is true (otherwise it is dropped, see ProcessLog.dropped), and turning
// stdinEnabled off while it runs closes its stdin. startDetached() launches
// without stdin and leaves `running` false. A test ends a run with
// finish(exitCode): running goes false and `exited` is raised.
QtObject {
    id: process

    property var command: []
    property bool running: false
    property bool stdinEnabled: false
    property var environment: ({})
    property bool clearEnvironment: false
    property string workingDirectory: ""
    property QtObject stdout: null
    property QtObject stderr: null
    property var processId: null
    // What reached this process's stdin, one entry per write()
    property var written: []
    // Index of the current run in ProcessLog.runs, -1 when none
    property int runIndex: -1
    signal started
    signal exited(int exitCode, int exitStatus)

    property bool _completed: false

    function write(data) {
        if (!running || !stdinEnabled || runIndex < 0) {
            ProcessLog.drop(command, data);
            return;
        }
        written = written.concat([data]);
        const run = ProcessLog.runs[runIndex];
        ProcessLog.update(runIndex, {
            "stdin": (run ? run.stdin : "") + String(data)
        });
    }
    function startDetached() {
        ProcessLog.launch(command, true);
    }
    // Quickshell's exec(): a command list, or {command, environment, ...}
    function exec(context) {
        if (Array.isArray(context))
            command = context;
        else if (context && context.command)
            command = context.command;
        if (running)
            running = false;
        running = true;
    }
    // Test helper: the process ends
    function finish(exitCode) {
        if (!running)
            return;
        const index = runIndex;
        running = false;
        ProcessLog.update(index, {
            "exited": exitCode === undefined ? 0 : exitCode
        });
        exited(exitCode === undefined ? 0 : exitCode, 0);
    }

    function _start() {
        runIndex = ProcessLog.launch(command, false);
        written = [];
        processId = 1000 + runIndex;
        ProcessLog.announce(process);
    }

    onRunningChanged: {
        if (!_completed)
            return;
        if (running)
            _start();
        else
            runIndex = -1;
    }
    onStdinEnabledChanged: {
        if (!stdinEnabled && running && runIndex >= 0)
            ProcessLog.update(runIndex, {
                "stdinClosed": true
            });
    }

    Component.onCompleted: {
        _completed = true;
        ProcessLog.born(process);
        // Declared `running: true`: the real one launches once complete
        if (running)
            _start();
    }
}
