import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Admin panel. Shows login, account list, and payout confirmation.
// All texts come from the Python i18n layer via admin.text(key).
// No business rules here: the services decide, the bridge forwards.
Item {
    id: root
    required property var admin
    property string adminCardUid: ""

    property int selectedAccountId: -1
    property bool cashOk: false
    property bool warningOk: false
    property bool finalOk: false

    implicitWidth: 1024
    implicitHeight: 768

    Rectangle {
        anchors.fill: parent
        color: "#111418"
    }

    // ---- login -----------------------------------------------------------
    ColumnLayout {
        id: loginView
        anchors.centerIn: parent
        spacing: 24
        visible: !root.admin.loggedIn

        Text {
            Layout.alignment: Qt.AlignHCenter
            text: root.admin.text("admin.login.prompt")
            color: "#ffffff"
            font.pixelSize: 28
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
        }

        TextField {
            id: pinField
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 320
            Layout.preferredHeight: 72
            placeholderText: root.admin.text("admin.login.pin_label")
            echoMode: TextInput.Password
            font.pixelSize: 28
            inputMethodHints: Qt.ImhDigitsOnly
        }

        Button {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 320
            Layout.preferredHeight: 80
            text: root.admin.text("admin.login.submit")
            font.pixelSize: 28
            onClicked: {
                // The admin card UID is supplied by the card reader in production,
                // never typed by the user. Until the reader is wired, the card UID
                // comes from root.adminCardUid, which the app sets.
                root.admin.login(root.adminCardUid, pinField.text)
                pinField.text = ""
            }
        }

        Text {
            Layout.alignment: Qt.AlignHCenter
            text: root.admin.message
            color: "#ffb4a8"
            font.pixelSize: 22
            visible: root.admin.message !== ""
        }
    }

    // ---- logged in: accounts --------------------------------------------
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16
        visible: root.admin.loggedIn && root.selectedAccountId < 0

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: root.admin.text("admin.accounts.title")
                color: "#ffffff"
                font.pixelSize: 32
                Layout.fillWidth: true
            }
            Button {
                Layout.preferredHeight: 64
                text: root.admin.text("admin.logout")
                font.pixelSize: 24
                onClicked: root.admin.logout()
            }
        }

        ListView {
            id: accountList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 12
            model: root.admin.accounts
            delegate: Rectangle {
                required property var modelData
                width: accountList.width
                height: 80
                radius: 8
                color: "#1f2630"
                border.color: "#5b6b7d"
                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        root.selectedAccountId = modelData.accountId
                        root.cashOk = false
                        root.warningOk = false
                        root.finalOk = false
                    }
                }
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    Text { text: modelData.statusText; color: "#ffffff"; font.pixelSize: 24 }
                    Item { Layout.fillWidth: true }
                    Text { text: modelData.balanceText; color: "#ffffff"; font.pixelSize: 24 }
                }
            }
            Text {
                anchors.centerIn: parent
                visible: accountList.count === 0
                text: root.admin.text("admin.accounts.empty")
                color: "#c9d1d9"
                font.pixelSize: 24
            }
        }
    }

    // ---- account detail and payout ----------------------------------------
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16
        visible: root.admin.loggedIn && root.selectedAccountId >= 0

        Text {
            text: root.admin.text("admin.payout.start")
            color: "#ffffff"
            font.pixelSize: 32
        }

        Text {
            Layout.fillWidth: true
            text: root.admin.text("admin.payout.warning_open_cards")
            color: "#ffd479"
            font.pixelSize: 22
            wrapMode: Text.WordWrap
        }

        CheckBox {
            text: root.admin.text("admin.payout.ack")
            font.pixelSize: 24
            checked: root.warningOk
            onToggled: root.warningOk = checked
        }

        CheckBox {
            text: root.admin.text("admin.payout.cash_handed_over")
            font.pixelSize: 24
            checked: root.cashOk
            onToggled: root.cashOk = checked
        }

        CheckBox {
            text: root.admin.text("admin.payout.final")
            font.pixelSize: 24
            checked: root.finalOk
            onToggled: root.finalOk = checked
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 16

            Button {
                Layout.preferredHeight: 80
                Layout.fillWidth: true
                text: root.admin.text("admin.payout.cancel")
                font.pixelSize: 24
                onClicked: root.selectedAccountId = -1
            }

            Button {
                Layout.preferredHeight: 80
                Layout.fillWidth: true
                text: root.admin.text("admin.payout.final")
                font.pixelSize: 24
                enabled: root.cashOk && root.warningOk && root.finalOk
                onClicked: {
                    root.admin.payout(root.selectedAccountId, root.cashOk, root.warningOk, root.finalOk)
                    root.selectedAccountId = -1
                }
            }
        }

        Text {
            text: root.admin.message
            color: "#c9d1d9"
            font.pixelSize: 22
            visible: root.admin.message !== ""
        }
    }

    Component.onCompleted: root.admin.refreshAccounts()
}
