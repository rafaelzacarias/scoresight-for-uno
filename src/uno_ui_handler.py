from functools import partial
from PySide6.QtGui import QStandardItemModel, QStandardItem, QFont
from PySide6.QtCore import Qt, QObject, Signal

from text_detection_target import TextDetectionTarget
from ui_mainwindow import Ui_MainWindow
from uno_output import UNOAPI
from sc_logging import logger
from storage import fetch_data, store_data

standard_uno_mapping = {
    "Time": "SetMatchTime",
    "Home Score": "SetGoalsHome",
    "Away Score": "SetGoalsAway",
    "Period": "SetPeriod",
}


class _LogSignalEmitter(QObject):
    """Helper QObject that allows emitting log messages from any thread
    and delivering them safely on the Qt main thread via a queued signal."""

    log_message = Signal(str)
    test_finished = Signal()


class UNOUIHandler:
    def __init__(self, ui: Ui_MainWindow):
        self.ui = ui
        self.unoUpdater = None
        self.unoUiSetup()

    def globalSettingsChanged(self, settingName, value):
        store_data("scoresight.json", settingName, value)

    def unoConnectionChanged(self):
        self.unoUpdater = UNOAPI(
            self.ui.lineEdit_unoUrl.text(),
            {},
        )
        self._setup_log_callback()
        self.globalSettingsChanged("uno_url", self.ui.lineEdit_unoUrl.text())
        self.unoMappingChanged(True)

    def unoMappingChanged(self, shouldUpdateStorage: bool):
        mapping = {}
        model = self.ui.tableView_unoMapping.model()
        if isinstance(model, QStandardItemModel):
            for i in range(model.rowCount()):
                item = model.item(i, 0)
                value = model.item(i, 1)
                if item and value:
                    mapping[item.text()] = value.text()
            if shouldUpdateStorage:
                self.globalSettingsChanged("uno_mapping", mapping)
            self.unoUpdater.set_field_mapping(mapping)
        else:
            logger.error("unoMappingChanged: model is not a QStandardItemModel")

    def unoUiSetup(self):
        # populate the UNO connection from storage
        self.ui.lineEdit_unoUrl.setText(
            fetch_data(
                "scoresight.json",
                "uno_url",
                "https://app.overlays.uno/apiv2/controlapps/.../api",
            )
        )
        # connect the lineEdit to unoConnectionChanged
        self.ui.lineEdit_unoUrl.textChanged.connect(self.unoConnectionChanged)

        # create the unoUpdater
        self.unoUpdater = UNOAPI(
            self.ui.lineEdit_unoUrl.text(),
            {},
        )

        # Setup log terminal
        self._setup_log_terminal()
        self._setup_log_callback()

        # add standard item model to the tableView_unoMapping
        self.ui.tableView_unoMapping.setModel(QStandardItemModel())
        mapping = fetch_data("scoresight.json", "uno_mapping", {})
        if mapping:
            self.unoUpdater.set_field_mapping(mapping)

        self.ui.tableView_unoMapping.model().dataChanged.connect(self.unoMappingChanged)

        self.ui.toolButton_toggleUno.toggled.connect(self.toggleUNO)

        # Connect the "Send Same?" checkbox
        self.ui.checkBox_uno_send_same.setChecked(
            fetch_data("scoresight.json", "uno_send_same", False)
        )
        self.ui.checkBox_uno_send_same.stateChanged.connect(
            partial(self.globalSettingsChanged, "uno_send_same")
        )

        # connect the "essentials" checkbox
        self.ui.checkBox_uno_essentials.setChecked(
            fetch_data("scoresight.json", "uno_essentials", False)
        )
        self.ui.checkBox_uno_essentials.stateChanged.connect(self.set_uno_essentials)
        # show/ hide widget_uno_essentials_details based on the checkbox
        self.ui.widget_uno_essentials_details.setVisible(
            self.ui.checkBox_uno_essentials.isChecked()
        )

        # connect lineEdit_uno_essentials_id
        self.ui.lineEdit_uno_essentials_id.setText(
            fetch_data("scoresight.json", "uno_essentials_id", "")
        )
        self.ui.lineEdit_uno_essentials_id.textChanged.connect(
            partial(self.globalSettingsChanged, "uno_essentials_id")
        )

        # Connect the "overlays format" checkbox if it exists
        if hasattr(self.ui, "checkBox_uno_overlays_format"):
            self.ui.checkBox_uno_overlays_format.setChecked(
                fetch_data("scoresight.json", "uno_overlays_format", False)
            )
            self.ui.checkBox_uno_overlays_format.stateChanged.connect(
                self.set_uno_overlays_format
            )

            # connect lineEdit_uno_subcomposition_id if it exists
            if hasattr(self.ui, "lineEdit_uno_subcomposition_id"):
                self.ui.lineEdit_uno_subcomposition_id.setText(
                    fetch_data("scoresight.json", "uno_subcomposition_id", "")
                )
                self.ui.lineEdit_uno_subcomposition_id.textChanged.connect(
                    partial(self.globalSettingsChanged, "uno_subcomposition_id")
                )

                # Create or find the widget container for overlays details
                if hasattr(self.ui, "widget_uno_overlays_details"):
                    self.ui.widget_uno_overlays_details.setVisible(
                        self.ui.checkBox_uno_overlays_format.isChecked()
                    )
        else:
            logger.debug(
                "UNO overlays format UI elements not found in UI file. "
                "Overlays format feature will not be available in the UI."
            )

    def _setup_log_terminal(self):
        """Configure the log terminal widget with monospace font and button connections."""
        self._log_emitter = _LogSignalEmitter()

        if hasattr(self.ui, "plainTextEdit_uno_log"):
            font = QFont("Courier")
            font.setStyleHint(QFont.StyleHint.Monospace)
            font.setPointSize(9)
            self.ui.plainTextEdit_uno_log.setFont(font)
            self._log_emitter.log_message.connect(
                self.ui.plainTextEdit_uno_log.appendPlainText
            )

        if hasattr(self.ui, "pushButton_uno_test"):
            self.ui.pushButton_uno_test.clicked.connect(self._test_connection)
            self._log_emitter.test_finished.connect(
                lambda: self.ui.pushButton_uno_test.setEnabled(True)
            )

        if hasattr(self.ui, "pushButton_uno_clear_log"):
            self.ui.pushButton_uno_clear_log.clicked.connect(self._clear_log)

    def _setup_log_callback(self):
        """Set the log callback on the current unoUpdater instance."""
        if self.unoUpdater:
            self.unoUpdater.set_log_callback(self._append_log)

    def _append_log(self, message):
        """Append a log message to the UNO log terminal widget (thread-safe)."""
        self._log_emitter.log_message.emit(message)

    def _test_connection(self):
        """Send a test request to verify the UNO endpoint connection."""
        if not self.unoUpdater:
            self._append_log("No UNO connection configured.")
            return
        if hasattr(self.ui, "pushButton_uno_test"):
            self.ui.pushButton_uno_test.setEnabled(False)
        self.unoUpdater.test_connection(on_finished=self._on_test_finished)

    def _on_test_finished(self):
        """Re-enable the test button after test_connection completes (thread-safe)."""
        self._log_emitter.test_finished.emit()

    def _clear_log(self):
        """Clear the UNO log terminal."""
        if hasattr(self.ui, "plainTextEdit_uno_log"):
            self.ui.plainTextEdit_uno_log.clear()

    def set_uno_essentials(self, value):
        self.globalSettingsChanged("uno_essentials", value)
        self.ui.widget_uno_essentials_details.setVisible(value)

    def set_uno_overlays_format(self, value):
        """Handle overlays format checkbox change."""
        self.globalSettingsChanged("uno_overlays_format", value)

        # Show/hide the subCompositionId input field
        if hasattr(self.ui, "widget_uno_overlays_details"):
            self.ui.widget_uno_overlays_details.setVisible(value)

        # When overlays format is enabled, hide Essentials options (not compatible)
        if value and hasattr(self.ui, "checkBox_uno_essentials"):
            # Disable essentials mode when overlays format is enabled
            if self.ui.checkBox_uno_essentials.isChecked():
                self.ui.checkBox_uno_essentials.setChecked(False)
            self.ui.checkBox_uno_essentials.setEnabled(False)
        elif hasattr(self.ui, "checkBox_uno_essentials"):
            # Re-enable essentials when overlays format is disabled
            self.ui.checkBox_uno_essentials.setEnabled(True)

    def toggleUNO(self, value):
        if not self.unoUpdater:
            return
        if value:
            self.ui.toolButton_toggleUno.setText("🛑")
            self.unoUpdater.start()
        else:
            self.ui.toolButton_toggleUno.setText("▶️")
            self.unoUpdater.stop()

    def updateUNOTable(self, detectionTargets: list[TextDetectionTarget]):
        mapping_storage = fetch_data("scoresight.json", "uno_mapping")
        model = QStandardItemModel()
        model.blockSignals(True)

        for box in detectionTargets:
            items = model.findItems(box.name, Qt.MatchFlag.MatchExactly)
            if len(items) == 0:
                row = model.rowCount()
                model.insertRow(row)
                model.setItem(row, 0, QStandardItem(box.name))
                model.item(row, 0).setFlags(Qt.ItemFlag.ItemIsEnabled)
            else:
                item = items[0]
                row = item.row()

            new_item_value = None
            if mapping_storage and box.name in mapping_storage:
                new_item_value = mapping_storage[box.name]
            else:
                if box.name in standard_uno_mapping:
                    new_item_value = standard_uno_mapping[box.name]
                else:
                    new_item_value = box.name
            model.setItem(row, 1, QStandardItem(new_item_value))

        for i in range(model.rowCount() - 1, -1, -1):
            item = model.item(i, 0)
            if not any([box.name == item.text() for box in detectionTargets]):
                model.removeRow(i)

        model.blockSignals(False)
        self.ui.tableView_unoMapping.setModel(model)
        self.ui.tableView_unoMapping.model().dataChanged.connect(self.unoMappingChanged)
        self.unoMappingChanged(False)
