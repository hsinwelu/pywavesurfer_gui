import sys
import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from matplotlib.backend_bases import key_press_handler
from scipy.signal import (
    butter, bessel, cheby2, ellip, firwin,
    sosfiltfilt, filtfilt, iirnotch,
)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QLabel, QFileDialog, QMessageBox, QSplitter,
    QComboBox, QTreeView, QDialog, QTreeWidget, QTreeWidgetItem,
    QGroupBox, QCheckBox, QDoubleSpinBox, QSpinBox, QScrollArea
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QFileSystemModel

from pywavesurfer import ws

class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        super(MplCanvas, self).__init__(self.fig)

class WaveSurferQtPlotter(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("PyWaveSurfer Plotter (Qt)")
        self.resize(1500, 850)

        self.ds = None
        self.file_path = None
        self._x_factor = 1.0
        self.settings = QSettings("pywavesurfer_gui", "WaveSurferQtPlotter")

        # Per-sweep cache so filters can re-render without re-reading the file
        self._sweep_data = None         # ndarray (n_channels, n_samples), raw
        self._sample_rate = None        # Hz
        self._duration = None           # seconds
        self._units = []                # per-channel y units
        self._current_sweep = None
        self._ch_checks = []            # one QCheckBox per channel

        # Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Left Panel — vertical splitter: folder browser on top, controls below
        left_panel = QWidget()
        left_outer = QVBoxLayout(left_panel)
        left_outer.setContentsMargins(0, 0, 0, 0)
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_outer.addWidget(left_splitter)

        # Folder browser
        browser = QWidget()
        browser_layout = QVBoxLayout(browser)

        folder_row = QHBoxLayout()
        self.folder_btn = QPushButton("Choose Folder")
        self.folder_btn.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.folder_btn)

        self.up_btn = QPushButton("↑ Up")
        self.up_btn.clicked.connect(self.go_up_folder)
        folder_row.addWidget(self.up_btn)
        browser_layout.addLayout(folder_row)

        self.folder_label = QLabel("No folder selected")
        self.folder_label.setWordWrap(True)
        browser_layout.addWidget(self.folder_label)

        self.fs_model = QFileSystemModel()
        self.fs_model.setNameFilters(["*.h5"])
        self.fs_model.setNameFilterDisables(False)

        self.file_tree = QTreeView()
        self.file_tree.setModel(self.fs_model)
        for col in range(1, 4):
            self.file_tree.hideColumn(col)
        self.file_tree.setHeaderHidden(True)
        self.file_tree.clicked.connect(self.on_tree_clicked)
        self.file_tree.doubleClicked.connect(self.on_tree_double_clicked)
        browser_layout.addWidget(self.file_tree)

        # Controls (existing widgets live here)
        controls = QWidget()
        left_layout = QVBoxLayout(controls)

        left_layout.addWidget(QLabel("Select a sweep:"))
        self.sweep_listbox = QListWidget()
        self.sweep_listbox.setMaximumHeight(140)
        self.sweep_listbox.itemClicked.connect(self.plot_selected)
        self.sweep_listbox.itemDoubleClicked.connect(self.plot_selected)
        left_layout.addWidget(self.sweep_listbox)

        # Metadata
        self.meta_btn = QPushButton("Show File Metadata")
        self.meta_btn.setEnabled(False)
        self.meta_btn.clicked.connect(self.show_metadata_window)
        left_layout.addWidget(self.meta_btn)
        self._meta_dialog = None

        # Unit Toggle
        left_layout.addWidget(QLabel("X-Axis Unit:"))
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["Seconds (s)", "Milliseconds (ms)"])
        self.unit_combo.currentIndexChanged.connect(self.change_units)
        left_layout.addWidget(self.unit_combo)

        left_layout.addStretch() # Push everything up

        left_splitter.addWidget(browser)
        left_splitter.addWidget(controls)
        left_splitter.setStretchFactor(0, 3)
        left_splitter.setStretchFactor(1, 1)
        left_splitter.setSizes([550, 200])

        # Right Panel (Plot)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        self.canvas = MplCanvas(self, width=8, height=6, dpi=100)
        self.canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.canvas.setFocus()
        
        # Connect Matplotlib's default keyboard shortcuts
        self.canvas.mpl_connect("key_press_event", lambda event: key_press_handler(event, self.canvas, self.toolbar))
        
        self.toolbar = NavigationToolbar(self.canvas, self)
        
        right_layout.addWidget(self.toolbar)
        right_layout.addWidget(self.canvas)

        # Filter Panel (right of plot)
        filter_panel = self._build_filter_panel()

        # Use splitter to allow resizing
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.addWidget(filter_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 6) # Give the plot the most space
        splitter.setStretchFactor(2, 3)
        splitter.setSizes([260, 880, 360])

        main_layout.addWidget(splitter)

        # Restore last folder if available, otherwise default to home
        last_dir = self.settings.value("last_folder", "")
        if not last_dir or not os.path.isdir(last_dir):
            last_dir = os.path.expanduser("~")
        self._set_folder(last_dir)

    def _build_filter_panel(self):
        """Construct the filter panel (channels + LP/HP/BP/Notch + Apply/Reset)."""
        outer = QScrollArea()
        outer.setWidgetResizable(True)
        panel = QWidget()
        outer.setWidget(panel)
        layout = QVBoxLayout(panel)

        title = QLabel("Filters (zero phase)")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        # Filter family (LP/HP/BP only; notch always uses iirnotch)
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Filter type:"))
        self.filter_family_combo = QComboBox()
        self.filter_family_combo.addItems(
            ["Butterworth", "Bessel", "Chebyshev II", "Elliptic", "FIR"]
        )
        self.filter_family_combo.currentTextChanged.connect(self._on_filter_family_changed)
        type_row.addWidget(self.filter_family_combo)

        help_btn = QPushButton("?")
        help_btn.setFixedWidth(28)
        help_btn.setToolTip("About the filter types")
        help_btn.clicked.connect(self.show_filter_help)
        type_row.addWidget(help_btn)
        layout.addLayout(type_row)

        # IIR order (used by Butterworth / Bessel / Chebyshev II / Elliptic)
        order_row = QHBoxLayout()
        self.order_label = QLabel("IIR order:")
        order_row.addWidget(self.order_label)
        self.order_spin = QSpinBox()
        self.order_spin.setRange(1, 10)
        self.order_spin.setValue(4)
        order_row.addWidget(self.order_spin)

        order_help_btn = QPushButton("?")
        order_help_btn.setFixedWidth(28)
        order_help_btn.setToolTip("What does the IIR order do?")
        order_help_btn.clicked.connect(self.show_order_taps_help)
        order_row.addWidget(order_help_btn)
        layout.addLayout(order_row)

        # FIR taps (used by FIR only — must be odd for HP / BP)
        fir_row = QHBoxLayout()
        self.fir_taps_label = QLabel("FIR taps:")
        fir_row.addWidget(self.fir_taps_label)
        self.fir_taps_spin = QSpinBox()
        self.fir_taps_spin.setRange(11, 9999)
        self.fir_taps_spin.setSingleStep(2)
        self.fir_taps_spin.setValue(401)
        fir_row.addWidget(self.fir_taps_spin)

        taps_help_btn = QPushButton("?")
        taps_help_btn.setFixedWidth(28)
        taps_help_btn.setToolTip("What do FIR taps do?")
        taps_help_btn.clicked.connect(self.show_order_taps_help)
        fir_row.addWidget(taps_help_btn)
        layout.addLayout(fir_row)

        # Channels group (dynamic checkboxes)
        self.channels_group = QGroupBox("Channels to filter")
        self._channels_layout = QVBoxLayout(self.channels_group)
        self._channels_placeholder = QLabel("(load a sweep)")
        self._channels_layout.addWidget(self._channels_placeholder)
        layout.addWidget(self.channels_group)

        # Low-pass
        lp_group = QGroupBox()
        lp_layout = QVBoxLayout(lp_group)
        self.lp_enable = QCheckBox("Low-pass")
        lp_layout.addWidget(self.lp_enable)
        lp_row = QHBoxLayout()
        lp_row.addWidget(QLabel("Cutoff (Hz):"))
        self.lp_cutoff = QDoubleSpinBox()
        self.lp_cutoff.setRange(0.01, 1e6)
        self.lp_cutoff.setDecimals(2)
        self.lp_cutoff.setValue(2000.0)
        lp_row.addWidget(self.lp_cutoff)
        lp_layout.addLayout(lp_row)
        layout.addWidget(lp_group)

        # High-pass
        hp_group = QGroupBox()
        hp_layout = QVBoxLayout(hp_group)
        self.hp_enable = QCheckBox("High-pass")
        hp_layout.addWidget(self.hp_enable)
        hp_row = QHBoxLayout()
        hp_row.addWidget(QLabel("Cutoff (Hz):"))
        self.hp_cutoff = QDoubleSpinBox()
        self.hp_cutoff.setRange(0.001, 1e6)
        self.hp_cutoff.setDecimals(3)
        self.hp_cutoff.setValue(1.0)
        hp_row.addWidget(self.hp_cutoff)
        hp_layout.addLayout(hp_row)
        layout.addWidget(hp_group)

        # Band-pass
        bp_group = QGroupBox()
        bp_layout = QVBoxLayout(bp_group)
        self.bp_enable = QCheckBox("Band-pass")
        bp_layout.addWidget(self.bp_enable)
        bp_lo = QHBoxLayout()
        bp_lo.addWidget(QLabel("Low (Hz):"))
        self.bp_low = QDoubleSpinBox()
        self.bp_low.setRange(0.001, 1e6)
        self.bp_low.setDecimals(3)
        self.bp_low.setValue(300.0)
        bp_lo.addWidget(self.bp_low)
        bp_layout.addLayout(bp_lo)
        bp_hi = QHBoxLayout()
        bp_hi.addWidget(QLabel("High (Hz):"))
        self.bp_high = QDoubleSpinBox()
        self.bp_high.setRange(0.001, 1e6)
        self.bp_high.setDecimals(3)
        self.bp_high.setValue(3000.0)
        bp_hi.addWidget(self.bp_high)
        bp_layout.addLayout(bp_hi)
        layout.addWidget(bp_group)

        # Notch
        notch_group = QGroupBox()
        notch_layout = QVBoxLayout(notch_group)
        self.notch_enable = QCheckBox("Notch (mains)")
        notch_layout.addWidget(self.notch_enable)
        nf = QHBoxLayout()
        nf.addWidget(QLabel("Freq (Hz):"))
        self.notch_freq = QDoubleSpinBox()
        self.notch_freq.setRange(0.1, 1e6)
        self.notch_freq.setDecimals(2)
        self.notch_freq.setValue(60.0)
        nf.addWidget(self.notch_freq)
        notch_layout.addLayout(nf)
        nq = QHBoxLayout()
        nq.addWidget(QLabel("Q factor:"))
        self.notch_q = QDoubleSpinBox()
        self.notch_q.setRange(0.1, 1000)
        self.notch_q.setDecimals(1)
        self.notch_q.setValue(30.0)
        nq.addWidget(self.notch_q)
        notch_layout.addLayout(nq)
        layout.addWidget(notch_group)

        # Filter on/off toggle
        self.filter_toggle = QPushButton("Filter: OFF")
        self.filter_toggle.setCheckable(True)
        self.filter_toggle.setChecked(False)
        self.filter_toggle.toggled.connect(self._on_filter_toggle)
        self.filter_toggle.setStyleSheet(
            "QPushButton { padding: 6px; font-weight: bold; }"
            "QPushButton:checked { background-color: #2e7d32; color: white; }"
        )
        layout.addWidget(self.filter_toggle)

        layout.addStretch()

        # Re-render live whenever a parameter changes (only takes effect if toggle is ON)
        self.filter_family_combo.currentTextChanged.connect(self._on_filter_param_changed)
        self.order_spin.valueChanged.connect(self._on_filter_param_changed)
        self.fir_taps_spin.valueChanged.connect(self._on_filter_param_changed)
        for cb in (self.lp_enable, self.hp_enable, self.bp_enable, self.notch_enable):
            cb.toggled.connect(self._on_filter_param_changed)
        for sb in (self.lp_cutoff, self.hp_cutoff, self.bp_low, self.bp_high,
                   self.notch_freq, self.notch_q):
            sb.valueChanged.connect(self._on_filter_param_changed)

        # Set initial enabled state for order vs FIR taps
        self._on_filter_family_changed(self.filter_family_combo.currentText())
        return outer

    def _on_filter_family_changed(self, text):
        is_fir = (text == "FIR")
        self.order_spin.setEnabled(not is_fir)
        self.order_label.setEnabled(not is_fir)
        self.fir_taps_spin.setEnabled(is_fir)
        self.fir_taps_label.setEnabled(is_fir)

    def choose_folder(self):
        start = self.settings.value("last_folder", os.path.expanduser("~"))
        folder = QFileDialog.getExistingDirectory(self, "Choose Folder", start)
        if folder:
            self._set_folder(folder)

    def go_up_folder(self):
        current = self.settings.value("last_folder", os.path.expanduser("~"))
        current = os.path.abspath(current)
        parent = os.path.dirname(current)
        if parent and parent != current and os.path.isdir(parent):
            self._set_folder(parent)

    def _set_folder(self, folder):
        self.settings.setValue("last_folder", folder)
        self.folder_label.setText(folder)
        self.fs_model.setRootPath(folder)
        self.file_tree.setRootIndex(self.fs_model.index(folder))

    def on_tree_clicked(self, index):
        path = self.fs_model.filePath(index)
        if os.path.isfile(path) and path.lower().endswith(".h5"):
            self._load_path(path)

    def on_tree_double_clicked(self, index):
        path = self.fs_model.filePath(index)
        if os.path.isdir(path):
            self._set_folder(path)

    def _load_path(self, file_path):
        try:
            self.ds = ws.loadDataFile(file_path)
            self.file_path = file_path

            # Populate listbox with sweeps
            self.sweep_listbox.clear()
            sweeps = sorted([k for k in self.ds.keys() if k.startswith('sweep')])
            self.sweep_listbox.addItems(sweeps)

            # Metadata is shown on-demand via the dialog
            self.meta_btn.setEnabled('header' in self.ds)
            if self._meta_dialog is not None and self._meta_dialog.isVisible():
                self._populate_meta_tree(self._meta_dialog.findChild(QTreeWidget))

            if sweeps:
                self.sweep_listbox.setCurrentRow(0)
                self.plot_sweep(sweeps[0])
            else:
                QMessageBox.information(self, "Info", "No sweeps found in this file.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file:\n{str(e)}")

    def _clean_value(self, v):
        """Convert bytes to string and handle lists/arrays for readability."""
        if isinstance(v, bytes):
            return v.decode('utf-8', errors='replace')
        if isinstance(v, (list, np.ndarray)):
            cleaned = [self._clean_value(i) for i in v]
            if len(cleaned) == 1:
                return str(cleaned[0])
            return str(cleaned)
        return str(v)

    def show_metadata_window(self):
        """Open a separate window displaying the header as a tree."""
        if not self.ds or 'header' not in self.ds:
            return

        if self._meta_dialog is None:
            dialog = QDialog(self)
            dialog.setWindowTitle("File Metadata (Header)")
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dialog.resize(600, 500)
            layout = QVBoxLayout(dialog)

            tree = QTreeWidget()
            tree.setColumnCount(2)
            tree.setHeaderLabels(["Property", "Value"])
            tree.itemDoubleClicked.connect(self._show_meta_leaf_detail)
            layout.addWidget(tree)

            dialog.destroyed.connect(self._on_meta_dialog_closed)
            self._meta_dialog = dialog

        self._populate_meta_tree(self._meta_dialog.findChild(QTreeWidget))
        self._meta_dialog.show()
        self._meta_dialog.raise_()
        self._meta_dialog.activateWindow()

    def _on_meta_dialog_closed(self, _obj=None):
        self._meta_dialog = None

    def _populate_meta_tree(self, tree):
        if tree is None or not self.ds or 'header' not in self.ds:
            return
        tree.clear()
        self._add_meta_items(tree, self.ds['header'])
        tree.expandToDepth(0)
        tree.resizeColumnToContents(0)

    def _add_meta_items(self, parent, data):
        """Recursively add header keys/values as QTreeWidgetItems."""
        if not isinstance(data, dict):
            return
        for k, v in data.items():
            item = QTreeWidgetItem(parent, [str(k), ""])
            if isinstance(v, dict):
                self._add_meta_items(item, v)
            else:
                item.setText(1, self._clean_value(v))

    def _show_meta_leaf_detail(self, item, _column):
        """Pop a detail box for leaf nodes with potentially long values."""
        if item.childCount() > 0:
            return
        # Reconstruct dotted path from ancestors
        path_parts = []
        node = item
        while node is not None:
            path_parts.append(node.text(0))
            node = node.parent()
        path = ".".join(reversed(path_parts))
        QMessageBox.information(self, "Metadata Detail",
                                f"<b>Property:</b> {path}<br><br>"
                                f"<b>Value:</b> {item.text(1)}")

    def change_units(self):
        """Rescale x-data and xlim in place so zoom/pan is preserved."""
        if not self.canvas.fig.axes:
            return
        is_ms = self.unit_combo.currentIndex() == 1
        new_factor = 1000.0 if is_ms else 1.0
        if new_factor == self._x_factor:
            return
        scale = new_factor / self._x_factor

        for ax in self.canvas.fig.axes:
            for line in ax.get_lines():
                line.set_xdata(line.get_xdata() * scale)
            xmin, xmax = ax.get_xlim()
            ax.set_xlim(xmin * scale, xmax * scale)

        self.canvas.fig.axes[-1].set_xlabel("Time (ms)" if is_ms else "Time (s)")
        self._x_factor = new_factor

        self.canvas.draw_idle()
        # Refresh navigation history so 'Home' matches the rescaled view
        self.toolbar.update()
        self.toolbar.push_current()

    def plot_selected(self):
        selected_items = self.sweep_listbox.selectedItems()
        if not selected_items:
            return
        
        sweep_name = selected_items[0].text()
        self.plot_sweep(sweep_name)

    def plot_sweep(self, sweep_name):
        try:
            sweep_data = self.ds[sweep_name]['analogScans']
            header = self.ds['header']

            try:
                sample_rate = float(header['Acquisition']['SampleRate'])
                duration = float(header['Acquisition']['Duration'])
            except (KeyError, TypeError):
                if 'AcquisitionSampleRate' in header:
                    sample_rate = float(header['AcquisitionSampleRate'])
                else:
                    raise KeyError("Could not find SampleRate in header")
                duration = sweep_data.shape[1] / sample_rate

            # Extract Y-axis units from header
            units = []
            try:
                if 'AIChannelUnits' in header:
                    units = header['AIChannelUnits']
                elif 'Acquisition' in header and 'AnalogIn' in header['Acquisition']:
                    units = header['Acquisition']['AnalogIn']['ChannelUnits']
                if isinstance(units, (list, np.ndarray)):
                    units = [u.decode('utf-8') if isinstance(u, bytes) else str(u) for u in units]
                elif isinstance(units, bytes):
                    units = [units.decode('utf-8')]
            except Exception:
                units = []

            # Cache state for filtering / re-render
            self._sweep_data = np.asarray(sweep_data, dtype=np.float64)
            self._sample_rate = sample_rate
            self._duration = duration
            self._units = list(units) if units is not None else []
            self._current_sweep = sweep_name

            n_channels = self._sweep_data.shape[0]
            self._rebuild_channel_checks(n_channels)

            # Honor the on/off toggle for the initial render of this sweep
            if self.filter_toggle.isChecked():
                display_data = self._compute_filtered_data()
            else:
                display_data = self._sweep_data
            self._render_plot(display_data)

        except Exception as e:
            QMessageBox.critical(self, "Plotting Error", f"Failed to plot sweep:\n{str(e)}")

    def _render_plot(self, data, preserve_view=False):
        """Render the given (n_channels, n_samples) array on the canvas."""
        n_channels, n_samples = data.shape
        time = np.linspace(0, self._duration, n_samples)

        is_ms = self.unit_combo.currentIndex() == 1
        if is_ms:
            time = time * 1000
            unit_label = "Time (ms)"
            self._x_factor = 1000.0
        else:
            unit_label = "Time (s)"
            self._x_factor = 1.0

        # Snapshot the current view only when the caller asks us to (filter
        # apply / reset). New sweep / new file always autoscale.
        prev_xlim = None
        prev_ylims = None
        if preserve_view:
            prev_axes = list(self.canvas.fig.axes)
            if prev_axes:
                prev_xlim = prev_axes[0].get_xlim()
                if len(prev_axes) == n_channels:
                    prev_ylims = [ax.get_ylim() for ax in prev_axes]

        self.canvas.fig.clear()
        axes = self.canvas.fig.subplots(n_channels, 1, sharex=True, squeeze=False)

        for i in range(n_channels):
            ax = axes[i, 0]
            ax.plot(time, data[i, :], label=f"Channel {i}", linewidth=0.7)

            ch_unit = self._units[i] if i < len(self._units) else "Amp"
            ax.set_ylabel(f"Ch {i} ({ch_unit})")

            ax.grid(True, linestyle=':', linewidth=0.5)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)

            if i == 0:
                ax.set_title(f"File: {os.path.basename(self.file_path)} - {self._current_sweep}")
            if i == n_channels - 1:
                ax.set_xlabel(unit_label)

        self.canvas.fig.tight_layout()

        # Register the auto-scaled view as Home BEFORE applying any preserved zoom,
        # so the Home button always returns to the full xlim/ylim.
        self.toolbar.update()
        self.toolbar.push_current()

        # Restore the previous zoom on top, so the displayed view matches what the
        # user was looking at; Back / Home still work to reach the full view.
        if prev_ylims is not None:
            for i in range(n_channels):
                axes[i, 0].set_ylim(prev_ylims[i])
        if prev_xlim is not None:
            axes[0, 0].set_xlim(prev_xlim)  # sharex propagates
        if prev_xlim is not None or prev_ylims is not None:
            self.toolbar.push_current()

        self.canvas.draw()
        self.canvas.setFocus()

    def _rebuild_channel_checks(self, n_channels):
        """Replace channel checkboxes only if the channel count changed."""
        if len(self._ch_checks) == n_channels:
            return
        # Clear placeholder + existing checkboxes
        if self._channels_placeholder is not None:
            self._channels_layout.removeWidget(self._channels_placeholder)
            self._channels_placeholder.deleteLater()
            self._channels_placeholder = None
        for cb in self._ch_checks:
            self._channels_layout.removeWidget(cb)
            cb.deleteLater()
        self._ch_checks = []
        for i in range(n_channels):
            cb = QCheckBox(f"Channel {i}")
            cb.setChecked(True)
            cb.toggled.connect(self._on_filter_param_changed)
            self._channels_layout.addWidget(cb)
            self._ch_checks.append(cb)

    def _design(self, btype, freq_arg):
        """Design a filter for the current family. Returns ('sos', sos) or
        ('fir', taps), or None if frequencies are invalid for this fs."""
        if self._sample_rate is None or self._sample_rate <= 0:
            return None
        fs = float(self._sample_rate)
        nyq = fs / 2.0

        if btype == 'band':
            lo, hi = freq_arg
            if not (0 < lo < hi < nyq):
                return None
            Wn = [lo / nyq, hi / nyq]
            fir_cutoff = [lo, hi]
        else:
            if not (0 < freq_arg < nyq):
                return None
            Wn = freq_arg / nyq
            fir_cutoff = freq_arg

        family = self.filter_family_combo.currentText()

        if family == "FIR":
            numtaps = self.fir_taps_spin.value()
            if numtaps % 2 == 0:
                numtaps += 1  # FIR HP / BP require odd length
            pass_zero = (btype == 'low')
            taps = firwin(numtaps, fir_cutoff, fs=fs, pass_zero=pass_zero)
            return ('fir', taps)

        order = self.order_spin.value()
        if family == "Butterworth":
            sos = butter(order, Wn, btype=btype, output='sos')
        elif family == "Bessel":
            sos = bessel(order, Wn, btype=btype, output='sos', norm='mag')
        elif family == "Chebyshev II":
            sos = cheby2(order, 40.0, Wn, btype=btype, output='sos')
        elif family == "Elliptic":
            sos = ellip(order, 1.0, 40.0, Wn, btype=btype, output='sos')
        else:
            return None
        return ('sos', sos)

    def _apply_design(self, design, data, selected):
        if design is None:
            return
        kind, coef = design
        if kind == 'sos':
            # sosfiltfilt's padlen defaults to ~6*n_sections; require signal longer
            min_len = 6 * coef.shape[0]
            for ch in selected:
                if data.shape[1] > min_len:
                    data[ch] = sosfiltfilt(coef, data[ch])
        elif kind == 'fir':
            min_len = 3 * len(coef)
            for ch in selected:
                if data.shape[1] > min_len:
                    data[ch] = filtfilt(coef, [1.0], data[ch])

    def _compute_filtered_data(self):
        """Apply enabled filters (zero-phase) to the selected channels."""
        if self._sweep_data is None:
            return None
        data = self._sweep_data.copy()
        if self._sample_rate is None or self._sample_rate <= 0:
            return data

        selected = [i for i, cb in enumerate(self._ch_checks) if cb.isChecked()]
        if not selected:
            return data

        try:
            if self.hp_enable.isChecked():
                self._apply_design(self._design('high', self.hp_cutoff.value()), data, selected)
            if self.lp_enable.isChecked():
                self._apply_design(self._design('low', self.lp_cutoff.value()), data, selected)
            if self.bp_enable.isChecked():
                self._apply_design(self._design('band', [self.bp_low.value(), self.bp_high.value()]), data, selected)
            if self.notch_enable.isChecked():
                fs = float(self._sample_rate)
                f0 = self.notch_freq.value()
                q = self.notch_q.value()
                if 0 < f0 < fs / 2.0 and q > 0:
                    b, a = iirnotch(f0, q, fs)
                    min_len = 3 * max(len(a), len(b))
                    for ch in selected:
                        if data.shape[1] > min_len:
                            data[ch] = filtfilt(b, a, data[ch])
        except Exception as e:
            QMessageBox.warning(self, "Filter Error", f"Filter failed: {e}\nShowing raw data.")
            return self._sweep_data.copy()

        return data

    def _on_filter_toggle(self, checked):
        self.filter_toggle.setText("Filter: ON" if checked else "Filter: OFF")
        if self._sweep_data is None:
            return
        data = self._compute_filtered_data() if checked else self._sweep_data
        self._render_plot(data, preserve_view=True)

    def _on_filter_param_changed(self, *_):
        """Live update: re-render only if filtering is currently on."""
        if self._sweep_data is None or not self.filter_toggle.isChecked():
            return
        self._render_plot(self._compute_filtered_data(), preserve_view=True)

    def show_filter_help(self):
        if getattr(self, "_filter_help_dialog", None) is None:
            dialog = QDialog(self)
            dialog.setWindowTitle("Filter Types — Guide")
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dialog.resize(640, 700)
            v = QVBoxLayout(dialog)

            text = QLabel()
            text.setTextFormat(Qt.TextFormat.RichText)
            text.setWordWrap(True)
            text.setText(
                "<h3>What does a filter actually do?</h3>"
                "<p>A filter keeps the parts of your signal that oscillate at the rates "
                "you care about, and removes the rest. Three terms to know before reading on:</p>"
                "<ul>"
                "<li><b>Frequency</b> — how fast something wiggles, measured in Hz "
                "(cycles per second). Slow events (baseline drift, slow membrane potential "
                "changes, subthreshold EPSPs) live at <i>low</i> frequencies; fast events "
                "(action potentials, electronic noise) live at <i>high</i> frequencies.</li>"
                "<li><b>Cutoff frequency</b> — the boundary you choose. A low-pass at 2 kHz "
                "keeps everything below 2 kHz and starts to remove what's above.</li>"
                "<li><b>Rolloff</b> — how sharply the filter transitions from \"kept\" to "
                "\"removed\" near the cutoff. Sharp rolloff = hard boundary; gentle rolloff = "
                "gradual fade.</li>"
                "</ul>"
                "<p>For <b>intracellular</b> and <b>juxtacellular</b> recordings, typical uses:</p>"
                "<ul>"
                "<li><b>Low-pass</b>: remove HF electronic noise above your AP / PSP bandwidth.</li>"
                "<li><b>High-pass</b>: remove slow baseline drift (electrode polarization, "
                "slow temperature changes).</li>"
                "<li><b>Notch</b>: kill mains pickup (50 Hz in EU/Asia, 60 Hz in US).</li>"
                "<li><b>Band-pass</b>: low-pass + high-pass in one step (e.g. isolate the "
                "spike band 300–3000 Hz for juxtacellular spike detection).</li>"
                "</ul>"

                "<h3>The five filter families</h3>"

                "<p><b>Butterworth — the safe default</b><br>"
                "Smooth, gradual rolloff with a flat passband. The kept signal is not "
                "distorted in amplitude.<br>"
                "<span style='color:#2e7d32'>+ No waveform distortion, predictable, well-behaved.</span><br>"
                "<span style='color:#b71c1c'>− Gentle rolloff lets HF noise close to cutoff bleed through "
                "unless you raise the order.</span><br>"
                "Good first choice for general intracellular work — current-clamp or "
                "voltage-clamp at moderate cutoffs.</p>"

                "<p><b>Bessel — preserve fast waveform shape</b><br>"
                "Bessel's defining feature is <i>near-linear phase</i>: every frequency "
                "component is delayed by the same amount, so the relative timing of fast "
                "features (e.g. AP rising edge, peak, AHP) is preserved with no distortion. "
                "The impulse response is also very smooth, so transients don't ring.<br>"
                "<span style='color:#2e7d32'>+ Best for preserving action potential and PSP shape — "
                "AP peaks, EPSP rise times, EPSC kinetics all stay accurate.</span><br>"
                "<span style='color:#b71c1c'>− Gentlest rolloff of all the IIR options; you need higher "
                "order to reject HF noise.</span><br>"
                "Excellent choice for <b>juxtacellular spike waveforms</b> and "
                "<b>intracellular current-clamp</b> recordings where AP / PSP shape "
                "matters. (Note: this app uses <code>filtfilt</code>, which makes the "
                "effective phase zero for any family, but Bessel's smooth impulse response "
                "still helps preserve fast transients.)</p>"

                "<p><b>Chebyshev II (inverse Chebyshev) — sharper, clean passband</b><br>"
                "Steeper rolloff than Butterworth, with the tradeoff hidden in the "
                "stopband (small ripples in the part you're discarding). The passband "
                "itself stays flat.<br>"
                "<span style='color:#2e7d32'>+ Stronger HF rejection at the same order as Butterworth, "
                "with no amplitude distortion of the kept signal.</span><br>"
                "<span style='color:#b71c1c'>− Steeper rolloff can introduce slightly more ringing on "
                "sharp transients (matters for AP onset, EPSC step).</span><br>"
                "Useful when Butterworth is letting noise through but you don't want to "
                "crank the order all the way up.</p>"

                "<p><b>Elliptic (Cauer) — the sharpest knife</b><br>"
                "Steepest possible rolloff for a given order, at the cost of <i>ripples in "
                "both the passband and the stopband</i>. Passband ripple = the kept signal "
                "is slightly distorted in amplitude.<br>"
                "<span style='color:#2e7d32'>+ Most aggressive HF rejection per order — useful when a "
                "noise band sits very close to a signal band you need to keep.</span><br>"
                "<span style='color:#b71c1c'>− Passband ripple = small but real amplitude distortion. "
                "Fine for spike <i>detection</i>, less ideal for quantitative PSP amplitude "
                "analysis.</span></p>"

                "<p><b>FIR (linear-phase, Hamming window)</b><br>"
                "A different kind of filter: instead of recursion, it computes each output "
                "as a weighted sum of recent input samples. Always stable, exactly linear "
                "phase, very predictable.<br>"
                "<span style='color:#2e7d32'>+ No stability issues, exact linear phase, full control "
                "of the frequency response — what you ask for is what you get.</span><br>"
                "<span style='color:#b71c1c'>− Long kernels produce edge transients at the start/end of "
                "the sweep — be careful on short voltage-clamp episodes.</span><br>"
                "Common in offline analysis pipelines (e.g. EEG / LFP), but also a clean "
                "choice for intracellular data when you want a precisely specified response.</p>"

                "<h3>Quick recipes (intracellular &amp; juxtacellular)</h3>"
                "<ul>"
                "<li><b>AP waveform (current-clamp or juxtacellular):</b> Bessel low-pass "
                "at ~5–10 kHz, order 4. Preserves spike shape; removes electronic noise.</li>"
                "<li><b>Subthreshold PSPs (current-clamp):</b> Butterworth low-pass at "
                "~1–2 kHz, plus high-pass at 0.1–1 Hz to remove slow baseline drift.</li>"
                "<li><b>EPSCs / IPSCs (voltage-clamp):</b> Butterworth low-pass at ~1–2 kHz "
                "(or Bessel if kinetics matter). Sample rate should be ≥10 kHz.</li>"
                "<li><b>Juxtacellular spike detection (timing only):</b> Butterworth "
                "band-pass 300–3000 Hz to isolate the spike band away from slow potentials "
                "and HF noise.</li>"
                "<li><b>Mains hum (50/60 Hz):</b> notch at 50 Hz (EU/Asia) or 60 Hz (US) "
                "with Q ≈ 30. Use <i>in addition to</i> your main filter.</li>"
                "</ul>"
                "<p style='background-color:#fff3cd; padding:8px; border-left:4px solid #ff9800;'>"
                "<b>⚠ Fast-membrane neurons (octopus cells, MSO neurons, etc.):</b><br>"
                "Cells with very short membrane time constants (τ on the order of "
                "a few hundred microseconds) have sub-millisecond EPSP and AP features. "
                "<b>Keep the low-pass cutoff above 5 kHz</b> — ideally 8–10 kHz with "
                "Bessel — otherwise the rising edges and peaks of fast PSPs and APs will "
                "be visibly attenuated and rounded, and you will <i>under-estimate</i> "
                "amplitudes and <i>over-estimate</i> rise times. The sample rate must "
                "match: aim for ≥40 kHz so a 10 kHz cutoff is comfortably below Nyquist."
                "</p>"

                "<h3>Troubleshooting — HF still leaking through low-pass?</h3>"
                "<ol>"
                "<li>Raise the order to 6–8.</li>"
                "<li>Switch to Chebyshev II (no passband distortion) or Elliptic (sharpest).</li>"
                "<li>Try FIR with ~801 taps.</li>"
                "<li>Sanity-check: the cutoff must be well below the Nyquist frequency "
                "(half the sampling rate). At fs = 20 kHz, Nyquist = 10 kHz, and a LP "
                "at 9 kHz can't possibly reject 9.5 kHz noise much.</li>"
                "</ol>"
            )

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(text)
            v.addWidget(scroll)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.close)
            v.addWidget(close_btn)

            dialog.destroyed.connect(self._on_filter_help_closed)
            self._filter_help_dialog = dialog

        self._filter_help_dialog.show()
        self._filter_help_dialog.raise_()
        self._filter_help_dialog.activateWindow()

    def _on_filter_help_closed(self, _obj=None):
        self._filter_help_dialog = None

    def show_order_taps_help(self):
        if getattr(self, "_order_help_dialog", None) is None:
            dialog = QDialog(self)
            dialog.setWindowTitle("IIR Order & FIR Taps — Guide")
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dialog.resize(640, 700)
            v = QVBoxLayout(dialog)

            text = QLabel()
            text.setTextFormat(Qt.TextFormat.RichText)
            text.setWordWrap(True)
            text.setText(
                "<h3>What do these numbers actually control?</h3>"
                "<p>Both <b>IIR order</b> and <b>FIR taps</b> are knobs for the same thing: "
                "<i>how sharply</i> the filter separates kept frequencies from removed ones. "
                "The bigger the number, the harder and more abrupt the boundary at your "
                "cutoff frequency.</p>"

                "<h3>IIR order</h3>"
                "<p>IIR stands for <b>infinite impulse response</b>: the filter computes "
                "each output sample partly from past outputs, in a recursive feedback loop. "
                "The <b>order</b> is the size of that feedback — bigger order = more "
                "complex recursion = sharper transition near the cutoff.</p>"
                "<p>A useful number to memorize: a Butterworth low-pass at order N attenuates "
                "by about <b>6·N dB per octave</b> above its cutoff (single pass). An "
                "<b>octave</b> means a doubling of frequency — so if your LP cutoff is "
                "2 kHz, the next octave is 4 kHz, then 8 kHz, etc.</p>"
                "<p>This app uses <code>filtfilt</code>, which runs the filter forward and "
                "backward — that doubles the effective slope. So you actually get "
                "<b>~12·N dB/octave</b>.</p>"
                "<table border='1' cellpadding='4' cellspacing='0'>"
                "<tr><th>Order N</th><th>Slope (with filtfilt)</th><th>Feel</th></tr>"
                "<tr><td>2</td><td>~24 dB/octave</td><td>Gentle — minimal ringing</td></tr>"
                "<tr><td>4</td><td>~48 dB/octave</td><td>Common default</td></tr>"
                "<tr><td>6</td><td>~72 dB/octave</td><td>Aggressive</td></tr>"
                "<tr><td>8</td><td>~96 dB/octave</td><td>Very steep — close to a wall</td></tr>"
                "</table>"
                "<p><b>How to read that:</b> &minus;48 dB means the amplitude is reduced "
                "to about <b>0.4%</b> of the original. So a Butterworth order-4 LP with "
                "filtfilt at 2 kHz cuts a 4 kHz noise component down to ~0.4% — usually plenty.</p>"

                "<p><b>What to pick (intracellular &amp; juxtacellular):</b></p>"
                "<ul>"
                "<li><b>Order 2:</b> very gentle, almost no ringing. Use when waveform "
                "fidelity is critical (intracellular AP shape) and you have moderate noise.</li>"
                "<li><b>Order 4 (default):</b> good balance for most current-clamp / "
                "voltage-clamp work. Sharp enough to suppress HF noise, gentle enough not "
                "to ring on PSPs / APs.</li>"
                "<li><b>Order 6–8:</b> when you specifically need a hard cutoff (e.g. "
                "isolating the juxtacellular spike band, or rejecting a strong adjacent "
                "noise peak). Use with Butterworth or Chebyshev II to keep the passband flat.</li>"
                "</ul>"
                "<p><b>Tradeoff to watch:</b> higher orders introduce more <i>ringing</i> "
                "around sharp transients — the AP rising edge or an EPSC step can develop "
                "small oscillations on either side. If you see that, drop the order or "
                "switch to Bessel.</p>"
                "<p><i>(Numerical note: we use second-order sections (SOS) internally, so "
                "you can safely go up to order 10 without coefficient blow-up.)</i></p>"

                "<h3>FIR taps</h3>"
                "<p>FIR stands for <b>finite impulse response</b>: each output sample is a "
                "weighted sum of recent input samples — no feedback. The <b>number of "
                "taps</b> is how many input samples participate in that sum, i.e. the "
                "length of the filter.</p>"
                "<ul>"
                "<li><b>More taps</b> → sharper transition, finer frequency control.</li>"
                "<li><b>Fewer taps</b> → wider transition, smaller artifacts at the sweep "
                "edges, faster computation.</li>"
                "</ul>"
                "<p>Rule of thumb for a Hamming-windowed FIR (what this app uses):<br>"
                "&nbsp;&nbsp;&nbsp;<b>transition width Δf ≈ fs / numtaps</b></p>"
                "<p>Example: at a sample rate of 20 kHz (typical for intracellular):</p>"
                "<table border='1' cellpadding='4' cellspacing='0'>"
                "<tr><th>Taps</th><th>Transition width</th><th>Typical use</th></tr>"
                "<tr><td>101</td><td>~200 Hz</td><td>Coarse — short voltage steps</td></tr>"
                "<tr><td>201</td><td>~100 Hz</td><td>Routine LP/HP</td></tr>"
                "<tr><td>401 (default)</td><td>~50 Hz</td><td>Standard for most work</td></tr>"
                "<tr><td>801</td><td>~25 Hz</td><td>Narrow transitions</td></tr>"
                "<tr><td>1601</td><td>~12 Hz</td><td>Very precise — long continuous recordings</td></tr>"
                "</table>"
                "<p><b>Tradeoff to watch — edge artifacts:</b> a long FIR kernel reaches "
                "further into the past and future of each sample. At the start and end of "
                "a sweep, <code>filtfilt</code> reflects the signal to handle the boundary, "
                "and that reflection can show up as a brief transient at the very edges. "
                "For typical intracellular sweeps (a few hundred ms to seconds), 401 taps "
                "is fine. For <b>short voltage-clamp episodes</b> (e.g. 50–100 ms), keep "
                "taps under ~50–100 to avoid eating into the data.</p>"
                "<p><b>What to pick:</b></p>"
                "<ul>"
                "<li><b>Default 401:</b> good for most intracellular and juxtacellular "
                "recordings at typical sample rates (10–50 kHz).</li>"
                "<li><b>801–1601:</b> when you need a narrow transition (e.g. very close to "
                "the mains line or to separate adjacent oscillation bands).</li>"
                "<li><b>~51–101:</b> when sweeps are very short and edge artifacts matter "
                "more than perfect frequency selectivity.</li>"
                "</ul>"
                "<p><i>(Note: we force the tap count to be odd so high-pass and band-pass "
                "FIR designs are well-defined.)</i></p>"
            )

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(text)
            v.addWidget(scroll)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.close)
            v.addWidget(close_btn)

            dialog.destroyed.connect(self._on_order_help_closed)
            self._order_help_dialog = dialog

        self._order_help_dialog.show()
        self._order_help_dialog.raise_()
        self._order_help_dialog.activateWindow()

    def _on_order_help_closed(self, _obj=None):
        self._order_help_dialog = None

if __name__ == "__main__":
    # High DPI scaling is handled automatically by PyQt6
    app = QApplication(sys.argv)
    window = WaveSurferQtPlotter()
    window.show()
    sys.exit(app.exec())
