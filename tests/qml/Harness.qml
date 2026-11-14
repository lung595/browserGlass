import QtQuick

// The assertions and the step runner the *.test.qml files share. run.sh puts
// it beside the tests, so a test just declares `Harness { id: t }`.
//
//   t.check("what", got, want)   deep comparison (JSON, keys sorted)
//   t.ok("what", condition)
//   t.steps([{run: fn}, {wait: 100, run: fn}, ...])
//                                runs each step after `wait` ms (default 0:
//                                the next turn of the event loop), then finish()
//   t.readFile("contract/sync.json")
//                                the text of a file of the test copy (the
//                                plugin root's files, contract/ fixtures),
//                                "" when missing
//   t.press(button)              what a click on a DButton does: clicked(),
//                                when the button is enabled
//   t.tap(toggle)                what a tap on a DToggle does: clicked() and
//                                toggled(!checked) (the owner binds checked)
//   t.finish()                   prints the tally and the HARNESS-DONE line
//                                run.sh requires, then exits: 0 when every
//                                check passed, 1 otherwise
// A test that checks nothing, or does not finish within timeoutMs, fails.
Item {
    id: harness

    property int failures: 0
    property int passes: 0
    property int timeoutMs: 30000
    property bool finished: false

    property var _steps: []
    property int _next: 0

    function stable(value) {
        if (Array.isArray(value))
            return "[" + value.map(v => stable(v)).join(",") + "]";
        if (value !== null && typeof value === "object") {
            const keys = Object.keys(value).sort();
            return "{" + keys.map(k => JSON.stringify(k) + ":" + stable(value[k])).join(",") + "}";
        }
        const s = JSON.stringify(value);
        return s === undefined ? "undefined" : s;
    }
    function press(button) {
        if (button.enabled)
            button.clicked();
    }
    function tap(toggle) {
        toggle.clicked();
        toggle.toggled(!toggle.checked);
    }
    function check(what, got, want) {
        const ok = stable(got) === stable(want);
        if (ok)
            passes++;
        else
            failures++;
        print((ok ? "ok   " : "FAIL ") + what + (ok ? "" : "  got " + stable(got) + " want " + stable(want)));
        return ok;
    }
    function ok(what, condition) {
        return check(what, !!condition, true);
    }
    function readFile(relPath) {
        const xhr = new XMLHttpRequest();
        xhr.open("GET", Qt.resolvedUrl(relPath), false);
        xhr.send();
        return xhr.status === 200 || xhr.status === 0 ? String(xhr.responseText || "") : "";
    }
    function finish() {
        if (finished)
            return;
        finished = true;
        guard.stop();
        stepper.stop();
        if (passes + failures === 0) {
            failures++;
            print("FAIL no check ran");
        }
        print(failures ? failures + " failure(s), " + passes + " passed" : "all " + passes + " passed");
        // run.sh fails a test whose output lacks this line (no Harness, or
        // Qt.quit() called directly)
        print("HARNESS-DONE " + (passes + failures) + " checks");
        Qt.exit(failures ? 1 : 0);
    }
    function steps(list) {
        _steps = list;
        _next = 0;
        _schedule();
    }
    function _schedule() {
        if (finished)
            return;
        if (_next >= _steps.length) {
            finish();
            return;
        }
        stepper.interval = Math.max(0, _steps[_next].wait || 0);
        stepper.restart();
    }

    Timer {
        id: stepper
        repeat: false
        onTriggered: {
            const step = harness._steps[harness._next++];
            try {
                step.run();
            } catch (e) {
                harness.failures++;
                print("FAIL step " + (harness._next - 1) + " threw: " + e);
            }
            harness._schedule();
        }
    }

    Timer {
        id: guard
        interval: harness.timeoutMs
        running: true
        onTriggered: {
            harness.failures++;
            print("FAIL timed out after " + harness.timeoutMs + " ms");
            harness.finish();
        }
    }
}
