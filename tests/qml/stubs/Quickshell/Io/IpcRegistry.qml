pragma Singleton
import QtQuick

// The live IpcHandler stand-ins, and a way to call them like the CLI does
QtObject {
    property var handlers: []

    function register(h) {
        handlers = handlers.concat([h]);
    }
    function unregister(h) {
        handlers = handlers.filter(x => x !== h);
    }
    function find(target) {
        return handlers.find(h => h.target === target && h.enabled) || null;
    }
    // Returns the function's answer as a string (what the CLI prints), or
    // null when no enabled handler has that target and function
    function call(target, name, ...args) {
        const h = find(target);
        if (!h || typeof h[name] !== "function")
            return null;
        const answer = h[name](...args);
        return answer === undefined ? "" : String(answer);
    }
}
