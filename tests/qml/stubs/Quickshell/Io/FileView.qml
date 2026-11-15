import QtQuick

// Stand-in for Quickshell's FileView: no disk access. What a file holds comes
// from FileViewLog.files[path] (shared by every view), or from `content` when
// a test sets it on one view. Setting `path` loads like the real one (loaded,
// or loadFailed(2) for a missing file; at once with blockLoading, otherwise
// on the next event loop turn). FileViewLog.change(path, text) plays an
// on-disk edit: the views watching that path get fileChanged, and, like the
// real one, they only re-read when the code calls reload() or text().
//
// Known gap: the real FileView has both a `loaded` signal and a `loaded` bool
// property; a QML object cannot declare both, so here `view.loaded` is the
// signal (always truthy). Plugin code must track loading itself (a flag set
// in onLoaded), never read `view.loaded` as a bool.
QtObject {
    id: view

    property string path: ""
    property bool watchChanges: false
    property bool blockLoading: false
    property bool blockAllReads: false
    property bool blockWrites: false
    property bool printErrors: true
    property bool preload: true
    property bool atomicWrites: true
    // A fake text for this view only; undefined: read FileViewLog.files
    property var content: undefined

    signal loaded
    signal loadFailed(int error)
    signal saved
    signal saveFailed(int error)
    signal fileChanged

    function exists() {
        return content !== undefined || FileViewLog.has(path);
    }
    function text() {
        if (blockAllReads)
            return "";
        if (content !== undefined)
            return String(content);
        return FileViewLog.read(path);
    }
    // The bytes of text() as UTF-8, like the real data()
    function data() {
        const bin = unescape(encodeURIComponent(text()));
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++)
            bytes[i] = bin.charCodeAt(i);
        return bytes.buffer;
    }
    // Writes at once; like the real one, blockWrites makes the write (and
    // `saved` or `saveFailed`) synchronous, otherwise they come on the next
    // turn. Like the real one, a text equal to the last one this view wrote
    // is not written again (even when the file went since). A path in
    // FileViewLog.failing fails to write (saveFailed, nothing stored).
    property var _written: undefined
    function setText(newText) {
        if (newText === _written)
            return;
        const failed = FileViewLog.failing.indexOf(path) >= 0;
        if (!failed) {
            _written = newText;
            FileViewLog.write(path, newText);
        }
        const done = () => failed ? view.saveFailed(13) : view.saved();
        if (blockWrites)
            done();
        else
            Qt.callLater(done);
    }
    function reload() {
        _load(true);
    }
    function _load(now) {
        if (path === "" || blockAllReads)
            return;
        const finish = () => {
            if (view.exists())
                view.loaded();
            else
                view.loadFailed(2);
        };
        if (now || blockLoading)
            finish();
        else
            Qt.callLater(finish);
    }

    onPathChanged: _load(false)
    Component.onCompleted: FileViewLog.born(view)
    Component.onDestruction: FileViewLog.died(view)
}
