import sys
import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from matplotlib.backend_bases import key_press_handler

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QLabel, QFileDialog, QMessageBox, QSplitter,
    QComboBox, QTreeView, QDialog, QTreeWidget, QTreeWidgetItem
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
        self.resize(1000, 700)

        self.ds = None
        self.file_path = None
        self._x_factor = 1.0
        self.settings = QSettings("pywavesurfer_gui", "WaveSurferQtPlotter")

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

        self.file_label = QLabel("No file loaded")
        self.file_label.setWordWrap(True)
        left_layout.addWidget(self.file_label)

        left_layout.addWidget(QLabel("Select a sweep:"))
        self.sweep_listbox = QListWidget()
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
        left_splitter.setStretchFactor(0, 1)
        left_splitter.setStretchFactor(1, 2)

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

        # Use splitter to allow resizing
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(1, 4) # Give more space to plot
        
        main_layout.addWidget(splitter)

        # Restore last folder if available, otherwise default to home
        last_dir = self.settings.value("last_folder", "")
        if not last_dir or not os.path.isdir(last_dir):
            last_dir = os.path.expanduser("~")
        self._set_folder(last_dir)

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
            self.file_label.setText(os.path.basename(file_path))

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

            n_channels, n_samples = sweep_data.shape
            time = np.linspace(0, duration, n_samples)
            
            # Extract Y-axis units from header
            units = []
            try:
                # Common location in many WaveSurfer versions
                if 'AIChannelUnits' in header:
                    units = header['AIChannelUnits']
                elif 'Acquisition' in header and 'AnalogIn' in header['Acquisition']:
                    units = header['Acquisition']['AnalogIn']['ChannelUnits']
                
                # Decode bytes if necessary
                if isinstance(units, (list, np.ndarray)):
                    units = [u.decode('utf-8') if isinstance(u, bytes) else str(u) for u in units]
                elif isinstance(units, bytes):
                    units = [units.decode('utf-8')]
            except Exception:
                units = []

            # Unit scaling
            is_ms = self.unit_combo.currentIndex() == 1
            if is_ms:
                time = time * 1000
                unit_label = "Time (ms)"
                self._x_factor = 1000.0
            else:
                unit_label = "Time (s)"
                self._x_factor = 1.0

            # Clear previous figure content
            self.canvas.fig.clear()
            
            # Create subplots (n_channels rows, 1 column)
            # sharex=True links the x-axes for synchronized zooming
            axes = self.canvas.fig.subplots(n_channels, 1, sharex=True, squeeze=False)
            
            for i in range(n_channels):
                ax = axes[i, 0]
                ax.plot(time, sweep_data[i, :], label=f"Channel {i}", linewidth=0.7)
                
                # Set Y label with unit if available
                ch_unit = units[i] if i < len(units) else "Amp"
                ax.set_ylabel(f"Ch {i} ({ch_unit})")
                
                ax.grid(True, linestyle=':', linewidth=0.5)
                
                # Remove top and right spines for a cleaner look
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
                
                if i == 0:
                    ax.set_title(f"File: {os.path.basename(self.file_path)} - {sweep_name}")
                if i == n_channels - 1:
                    ax.set_xlabel(unit_label)

            self.canvas.fig.tight_layout()
            self.canvas.draw()
            
            # Refresh toolbar and save the current view as the 'Home' position
            self.toolbar.update()
            self.toolbar.push_current()
            
            self.canvas.setFocus()

        except Exception as e:
            QMessageBox.critical(self, "Plotting Error", f"Failed to plot sweep:\n{str(e)}")

if __name__ == "__main__":
    # High DPI scaling is handled automatically by PyQt6
    app = QApplication(sys.argv)
    window = WaveSurferQtPlotter()
    window.show()
    sys.exit(app.exec())
