import QtQuick
import Quickshell.Io

// The Process stand-in: argv and stdin are recorded per launch, and the
// record survives the Process object.
Item {
    id: root

    Harness {
        id: t
    }

    property int startedCount: 0
    property var exitCodes: []

    Process {
        id: piped
        command: ["python3", "-I", "-c", "pass", "uninstall"]
        stdinEnabled: true
        onStarted: root.startedCount++
        onExited: (code, status) => root.exitCodes = root.exitCodes.concat([code])
    }

    Process {
        id: declared
        command: ["true"]
        running: true
    }

    property var gone: null
    Component {
        id: shortLived
        Process {
            command: ["sh", "-c", "exit 0"]
            stdinEnabled: true
        }
    }

    Component.onCompleted: {
        t.steps([
            {
                "run": () => {
                    t.check("a declared running process launched once", ProcessLog.commands(), [["true"]]);
                    ProcessLog.reset();
                    piped.write("lost");
                    t.check("a write before launch is dropped", ProcessLog.dropped, [[["python3", "-I", "-c", "pass", "uninstall"], "lost"]]);
                    piped.running = true;
                    piped.write("abc");
                    piped.write("def");
                    t.check("started comes on the next turn", root.startedCount, 0);
                    t.check("argv recorded", ProcessLog.last().command, ["python3", "-I", "-c", "pass", "uninstall"]);
                    t.check("stdin recorded", ProcessLog.last().stdin, "abcdef");
                    t.check("per-process writes", piped.written, ["abc", "def"]);
                    piped.stdinEnabled = false;
                    t.ok("closing stdin is recorded", ProcessLog.last().stdinClosed);
                    piped.write("late");
                    t.check("a write after closing is dropped", ProcessLog.dropped.length, 2);
                    t.check("still running", piped.running, true);
                }
            },
            {
                "run": () => {
                    t.check("started raised once", root.startedCount, 1);
                    piped.finish(3);
                    t.check("exited", root.exitCodes, [3]);
                    t.check("run record has the exit code", ProcessLog.last().exited, 3);
                    t.check("not running", piped.running, false);
                    piped.startDetached();
                    t.check("startDetached is recorded without stdin", [ProcessLog.last().detached, ProcessLog.last().stdin], [true, ""]);
                    t.check("and leaves running false", piped.running, false);
                    const p = shortLived.createObject(root);
                    p.running = true;
                    p.write("payload");
                    p.destroy();
                }
            },
            {
                "run": () => {
                    t.check("the record outlives the object", [ProcessLog.last().command, ProcessLog.last().stdin], [["sh", "-c", "exit 0"], "payload"]);
                    t.check("and the object left the live list", ProcessLog.alive().length, 2);
                    piped.exec(["echo", "hi"]);
                    t.check("exec launches", ProcessLog.last().command, ["echo", "hi"]);
                    piped.finish(0);
                }
            }
        ]);
    }
}
