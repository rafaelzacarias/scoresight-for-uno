from functools import partial
from PySide6.QtGui import QStandardItemModel, QStandardItem, QFont
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtWidgets import QComboBox, QLabel, QHBoxLayout, QWidget, QSpinBox

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
    subcompositions_received = Signal(list)
    rate_limit_updated = Signal(str)


class UNOUIHandler:
    def __init__(self, ui: Ui_MainWindow):
        self.ui = ui
        self.unoUpdater = None
        self.unoUiSetup()

    def globalSettingsChanged(self, settingName, value):
        store_data("scoresight.json", settingName, value)

    def unoConnectionChanged(self):
        raw_url = self.ui.lineEdit_unoUrl.text()
        self.unoUpdater = UNOAPI(
            raw_url,
            {},
        )
        self._setup_log_callback()
        self.globalSettingsChanged("uno_url", raw_url)
        self.unoMappingChanged(True)
        # Sync running state with the toggle button
        if self.ui.toolButton_toggleUno.isChecked():
            self.unoUpdater.start()
        # Re-apply rate limits
        if hasattr(self, '_spinBox_scores_interval'):
            self.unoUpdater.set_scores_interval(self._spinBox_scores_interval.value())
        if hasattr(self, '_spinBox_clock_interval'):
            self.unoUpdater.set_clock_interval(self._spinBox_clock_interval.value())
        # Re-apply sub-composition selections
        if hasattr(self, '_comboBox_subcomp_scores'):
            sc_id = self._comboBox_subcomp_scores.currentData()
            if sc_id:
                self.unoUpdater.subCompositionIdScores = sc_id
        if hasattr(self, '_comboBox_subcomp_clock'):
            sc_id = self._comboBox_subcomp_clock.currentData()
            if sc_id:
                self.unoUpdater.subCompositionIdClock = sc_id

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
        stored_url = fetch_data(
            "scoresight.json",
            "uno_url",
            "https://app.overlays.uno/control/.../",
        )
        self.ui.lineEdit_unoUrl.setText(stored_url)
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

        # Hide unused UI elements
        for widget_name in [
            "checkBox_uno_send_same", "checkBox_uno_essentials",
            "widget_uno_essentials_details", "spinBox", "label_23",
        ]:
            w = getattr(self.ui, widget_name, None)
            if w:
                w.hide()
        # Also hide overlays format widgets
        for widget_name in [
            "checkBox_uno_overlays_format", "widget_uno_overlays_details",
        ]:
            w = getattr(self.ui, widget_name, None)
            if w:
                w.hide()

        # --- Sub-Composition selector (populated on test connection) ---
        self._create_subcomposition_selector()

    def _create_subcomposition_selector(self):
        """Create Scores and Clock sub-composition dropdowns with rate-limit
        spinboxes and insert into the UNO tab layout."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 3, 0, 3)

        # --- Scores dropdown + rate limit ---
        label_scores = QLabel("Scores")
        layout.addWidget(label_scores)

        self._comboBox_subcomp_scores = QComboBox()
        self._comboBox_subcomp_scores.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self._comboBox_subcomp_scores.setPlaceholderText("Click Test Output...")
        layout.addWidget(self._comboBox_subcomp_scores)

        self._spinBox_scores_interval = QSpinBox()
        self._spinBox_scores_interval.setRange(1, 30)
        self._spinBox_scores_interval.setSuffix("s")
        self._spinBox_scores_interval.setToolTip("Seconds between score updates")
        saved_scores_interval = fetch_data("scoresight.json", "uno_scores_interval", 5)
        self._spinBox_scores_interval.setValue(saved_scores_interval)
        self.unoUpdater.set_scores_interval(saved_scores_interval)
        self._spinBox_scores_interval.valueChanged.connect(self._on_scores_interval_changed)
        layout.addWidget(self._spinBox_scores_interval)

        # --- Clock dropdown + rate limit ---
        label_clock = QLabel("Clock")
        layout.addWidget(label_clock)

        self._comboBox_subcomp_clock = QComboBox()
        self._comboBox_subcomp_clock.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self._comboBox_subcomp_clock.setPlaceholderText("Click Test Output...")
        layout.addWidget(self._comboBox_subcomp_clock)

        self._spinBox_clock_interval = QSpinBox()
        self._spinBox_clock_interval.setRange(1, 30)
        self._spinBox_clock_interval.setSuffix("s")
        self._spinBox_clock_interval.setToolTip("Seconds between clock updates")
        saved_clock_interval = fetch_data("scoresight.json", "uno_clock_interval", 1)
        self._spinBox_clock_interval.setValue(saved_clock_interval)
        self.unoUpdater.set_clock_interval(saved_clock_interval)
        self._spinBox_clock_interval.valueChanged.connect(self._on_clock_interval_changed)
        layout.addWidget(self._spinBox_clock_interval)

        # Insert the widget into the UNO tab layout before the mapping table
        parent_layout = self.ui.tableView_unoMapping.parentWidget().layout()
        if parent_layout:
            from PySide6.QtWidgets import QGridLayout
            if isinstance(parent_layout, QGridLayout):
                idx = parent_layout.indexOf(self.ui.tableView_unoMapping)
                if idx >= 0:
                    table_row, table_col, _, _ = parent_layout.getItemPosition(idx)
                else:
                    table_row = parent_layout.rowCount()
                to_shift = []
                for i in range(parent_layout.count()):
                    r, c, rs, cs = parent_layout.getItemPosition(i)
                    if r >= table_row:
                        w = parent_layout.itemAt(i).widget()
                        if w:
                            to_shift.append((w, r, c, rs, cs))
                for w, r, c, rs, cs in to_shift:
                    parent_layout.removeWidget(w)
                for w, r, c, rs, cs in to_shift:
                    parent_layout.addWidget(w, r + 1, c, rs, cs)
                parent_layout.addWidget(container, table_row, 0, 1,
                                        parent_layout.columnCount() or 1)
            else:
                tbl_idx = parent_layout.indexOf(self.ui.tableView_unoMapping)
                if tbl_idx >= 0:
                    parent_layout.insertWidget(tbl_idx, container)
                else:
                    parent_layout.addWidget(container)
        else:
            logger.error("Could not find UNO tab layout to insert sub-composition selector")

        # Restore saved selections
        saved_scores = fetch_data("scoresight.json", "uno_subcomposition_id_scores", "")
        if saved_scores:
            self._comboBox_subcomp_scores.addItem(saved_scores, saved_scores)
            self._comboBox_subcomp_scores.setCurrentIndex(0)
            if self.unoUpdater:
                self.unoUpdater.subCompositionIdScores = saved_scores

        saved_clock = fetch_data("scoresight.json", "uno_subcomposition_id_clock", "")
        if saved_clock:
            self._comboBox_subcomp_clock.addItem(saved_clock, saved_clock)
            self._comboBox_subcomp_clock.setCurrentIndex(0)
            if self.unoUpdater:
                self.unoUpdater.subCompositionIdClock = saved_clock

        # Connect selection changes
        self._comboBox_subcomp_scores.currentIndexChanged.connect(
            self._on_subcomp_scores_changed
        )
        self._comboBox_subcomp_clock.currentIndexChanged.connect(
            self._on_subcomp_clock_changed
        )

    def _on_subcomp_scores_changed(self, index):
        sc_id = self._comboBox_subcomp_scores.currentData()
        if sc_id and self.unoUpdater:
            self.unoUpdater.subCompositionIdScores = sc_id
            self.globalSettingsChanged("uno_subcomposition_id_scores", sc_id)
            logger.info(f"Scores sub-composition: {self._comboBox_subcomp_scores.currentText()} ({sc_id})")

    def _on_subcomp_clock_changed(self, index):
        sc_id = self._comboBox_subcomp_clock.currentData()
        if sc_id and self.unoUpdater:
            self.unoUpdater.subCompositionIdClock = sc_id
            self.globalSettingsChanged("uno_subcomposition_id_clock", sc_id)
            logger.info(f"Clock sub-composition: {self._comboBox_subcomp_clock.currentText()} ({sc_id})")

    def _on_scores_interval_changed(self, value):
        self.globalSettingsChanged("uno_scores_interval", value)
        if self.unoUpdater:
            self.unoUpdater.set_scores_interval(value)

    def _on_clock_interval_changed(self, value):
        self.globalSettingsChanged("uno_clock_interval", value)
        if self.unoUpdater:
            self.unoUpdater.set_clock_interval(value)

    def _populate_subcompositions(self, subcompositions):
        """Populate both sub-composition dropdowns from the test_connection response.

        Auto-selects the clock dropdown to whichever sub-composition contains
        an ``ocrClock`` field in its payload.
        """
        from uno_output import UNOAPI

        saved_scores = fetch_data("scoresight.json", "uno_subcomposition_id_scores", "")
        saved_clock = fetch_data("scoresight.json", "uno_subcomposition_id_clock", "")

        # Detect which subComposition contains a clock field
        clock_auto_index = -1
        for i, sc in enumerate(subcompositions):
            fields = sc.get("fields", [])
            if any(f in UNOAPI.CLOCK_FIELDS for f in fields):
                clock_auto_index = i
                break

        for combo, saved_id, auto_idx, label in [
            (self._comboBox_subcomp_scores, saved_scores, -1, "Scores"),
            (self._comboBox_subcomp_clock, saved_clock, clock_auto_index, "Clock"),
        ]:
            combo.blockSignals(True)
            combo.clear()
            select_index = -1
            for i, sc in enumerate(subcompositions):
                sc_id = sc["subCompositionId"]
                sc_name = sc["subCompositionName"]
                combo.addItem(sc_name, sc_id)
                if sc_id == saved_id:
                    select_index = i

            if select_index >= 0:
                combo.setCurrentIndex(select_index)
            elif auto_idx >= 0:
                combo.setCurrentIndex(auto_idx)
            elif combo.count() > 0:
                combo.setCurrentIndex(0)

            combo.blockSignals(False)

        # Fire selection handlers
        if self._comboBox_subcomp_scores.count() > 0:
            self._on_subcomp_scores_changed(self._comboBox_subcomp_scores.currentIndex())
        if self._comboBox_subcomp_clock.count() > 0:
            self._on_subcomp_clock_changed(self._comboBox_subcomp_clock.currentIndex())

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

        # Move Test Output button from the log section into the URL row
        if hasattr(self.ui, "pushButton_uno_test"):
            btn = self.ui.pushButton_uno_test
            # Remove from its current parent layout
            old_layout = btn.parentWidget().layout() if btn.parentWidget() else None
            if old_layout:
                old_layout.removeWidget(btn)
            # Add to the URL row layout (horizontalLayout_29), after the toggle button
            url_layout = self.ui.toolButton_toggleUno.parentWidget().layout()
            if url_layout:
                url_layout.addWidget(btn)
            btn.clicked.connect(self._test_connection)
            self._log_emitter.test_finished.connect(
                lambda: btn.setEnabled(True)
            )

        # Add rate limit label to the log buttons row
        self._label_rate_limit = QLabel("")
        self._label_rate_limit.setStyleSheet("color: #888; font-size: 10px;")
        if hasattr(self.ui, "horizontalLayout_uno_log_buttons"):
            self.ui.horizontalLayout_uno_log_buttons.addWidget(self._label_rate_limit)
        self._log_emitter.rate_limit_updated.connect(self._label_rate_limit.setText)

        # Connect subcompositions signal to populate dropdown on main thread
        self._log_emitter.subcompositions_received.connect(
            self._populate_subcompositions
        )

        if hasattr(self.ui, "pushButton_uno_clear_log"):
            self.ui.pushButton_uno_clear_log.clicked.connect(self._clear_log)

    def _setup_log_callback(self):
        """Set the log callback on the current unoUpdater instance."""
        if self.unoUpdater:
            self.unoUpdater.set_log_callback(self._append_log)
            self.unoUpdater.set_rate_limit_callback(self._rate_limit_callback)

    def _append_log(self, message):
        """Append a log message to the UNO log terminal widget (thread-safe)."""
        self._log_emitter.log_message.emit(message)

    def _rate_limit_callback(self, text):
        """Receive rate-limit info from the background thread (thread-safe)."""
        self._log_emitter.rate_limit_updated.emit(text)

    def _test_connection(self):
        """Send a test request to verify the UNO endpoint connection."""
        if not self.unoUpdater:
            self._append_log("No UNO connection configured.")
            return
        if hasattr(self.ui, "pushButton_uno_test"):
            self.ui.pushButton_uno_test.setEnabled(False)
        self.unoUpdater.test_connection(
            on_finished=self._on_test_finished,
            on_subcompositions=self._on_subcompositions_from_thread,
        )

    def _on_subcompositions_from_thread(self, subcompositions):
        """Called from the background thread; marshal to the Qt main thread."""
        self._log_emitter.subcompositions_received.emit(subcompositions)

    def _on_test_finished(self):
        """Re-enable the test button after test_connection completes (thread-safe)."""
        self._log_emitter.test_finished.emit()

    def _clear_log(self):
        """Clear the UNO log terminal."""
        if hasattr(self.ui, "plainTextEdit_uno_log"):
            self.ui.plainTextEdit_uno_log.clear()

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
