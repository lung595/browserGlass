import QtQuick

// Stand-in: no process runs, so a line only arrives when a test emits read()
QtObject {
    property string splitMarker: "\n"
    signal read(string data)
}
