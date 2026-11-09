import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Main kiosk window. Customer actions, status line, and admin availability.
// All texts come from the Python i18n layer via kiosk.text(key).
// No business rules here: the services decide, the bridge forwards.
Item {
    id: root
    required property var kiosk

    implicitWidth: 1024
    implicitHeight: 768

    Rectangle {
        anchors.fill: parent
        color: "#111418"
    }

    ColumnLayout {
        anchors.centerIn: parent
        spacing: 24

        Text {
            Layout.alignment: Qt.AlignHCenter
            text: root.kiosk.text("main.title")
            color: "#ffffff"
            font.pixelSize: 36
        }

        Button {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 480
            Layout.preferredHeight: 96
            text: root.kiosk.text("main.action.issue")
            onClicked: root.kiosk.startIssue()
        }

        Button {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 480
            Layout.preferredHeight: 96
            text: root.kiosk.text("main.action.topup")
            onClicked: root.kiosk.startTopup()
        }

        Text {
            Layout.alignment: Qt.AlignHCenter
            text: root.kiosk.status
            color: "#dddddd"
            font.pixelSize: 24
            wrapMode: Text.WordWrap
            Layout.maximumWidth: 720
            horizontalAlignment: Text.AlignHCenter
        }

        Text {
            Layout.alignment: Qt.AlignHCenter
            visible: !root.kiosk.adminAvailable
            text: root.kiosk.text("main.admin.unavailable")
            color: "#ffb347"
            font.pixelSize: 18
        }
    }
}
