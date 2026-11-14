import QtQuick

// Stand-in for a process's collected output
QtObject {
    property string text: ""
    signal streamFinished
}
