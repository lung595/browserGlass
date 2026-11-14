pragma Singleton
import QtQuick

// Test stand-in for the disk under FileView: path -> text, the live views,
// and every write. A test seeds files with put(), plays an outside edit with
// change() and reads what the code wrote in `writes` ([[path, text], ...]).
QtObject {
    property var files: ({})
    property var views: []
    property var writes: []

    function has(path) {
        return Object.prototype.hasOwnProperty.call(files, path);
    }
    function read(path) {
        return has(path) ? String(files[path]) : "";
    }
    function put(path, text) {
        const next = Object.assign({}, files);
        next[path] = text;
        files = next;
    }
    function write(path, text) {
        put(path, text);
        writes = writes.concat([[path, text]]);
    }
    function remove(path) {
        const next = Object.assign({}, files);
        delete next[path];
        files = next;
        notify(path);
    }
    // An edit made outside the shell: store it, then tell the watchers
    function change(path, text) {
        put(path, text);
        notify(path);
    }
    function notify(path) {
        for (const v of views.slice()) {
            if (v.path === path && v.watchChanges)
                v.fileChanged();
        }
    }
    function born(view) {
        views = views.concat([view]);
    }
    function died(view) {
        views = views.filter(v => v !== view);
    }
    function reset() {
        files = {};
        writes = [];
    }
}
