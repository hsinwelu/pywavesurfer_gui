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
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt

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

        # Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Left Panel (Controls)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        self.load_btn = QPushButton("Load .h5 File")
        self.load_btn.clicked.connect(self.load_file)
        left_layout.addWidget(self.load_btn)

        self.file_label = QLabel("No file loaded")
        self.file_label.setWordWrap(True)
        left_layout.addWidget(self.file_label)

        left_layout.addWidget(QLabel("Select a sweep:"))
        self.sweep_listbox = QListWidget()
        self.sweep_listbox.itemSelectionChanged.connect(self.on_selection_changed)
        self.sweep_listbox.itemDoubleClicked.connect(self.plot_selected)
        left_layout.addWidget(self.sweep_listbox)

        self.plot_btn = QPushButton("Plot Selected Sweep")
        self.plot_btn.setEnabled(False)
        self.plot_btn.clicked.connect(self.plot_selected)
        left_layout.addWidget(self.plot_btn)

        # Metadata Table
        left_layout.addWidget(QLabel("File Metadata (Header):"))
        self.meta_table = QTableWidget()
        self.meta_table.setColumnCount(2)
        self.meta_table.setHorizontalHeaderLabels(["Property", "Value"])
        self.meta_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.meta_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.meta_table.cellDoubleClicked.connect(self.show_meta_detail)
        left_layout.addWidget(self.meta_table)

        # Unit Toggle
        left_layout.addWidget(QLabel("X-Axis Unit:"))
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["Seconds (s)", "Milliseconds (ms)"])
        self.unit_combo.currentIndexChanged.connect(self.plot_selected)
        left_layout.addWidget(self.unit_combo)

        left_layout.addStretch() # Push everything up

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

    def load_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open HDF5 File", "", "HDF5 files (*.h5)")
        if not file_path:
            return

        try:
            self.ds = ws.loadDataFile(file_path)
            self.file_path = file_path
            self.file_label.setText(os.path.basename(file_path))
            
            # Populate listbox with sweeps
            self.sweep_listbox.clear()
            sweeps = sorted([k for k in self.ds.keys() if k.startswith('sweep')])
            self.sweep_listbox.addItems(sweeps)
            
            # Populate metadata table
            self.populate_metadata()
            
            if not sweeps:
                QMessageBox.information(self, "Info", "No sweeps found in this file.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file:\n{str(e)}")

    def populate_metadata(self):
        """Extracts and flattens header data to show in the table."""
        self.meta_table.setRowCount(0)
        if not self.ds or 'header' not in self.ds:
            return

        header = self.ds['header']
        
        def clean_value(v):
            """Convert bytes to string and handle lists/arrays for readability."""
            if isinstance(v, bytes):
                return v.decode('utf-8', errors='replace')
            if isinstance(v, (list, np.ndarray)):
                # If it's a list/array of bytes, clean each item
                cleaned_list = [clean_value(i) for i in v]
                if len(cleaned_list) == 1:
                    return str(cleaned_list[0])
                return str(cleaned_list)
            return str(v)

        def flatten(d, parent_key=''):
            items = []
            if isinstance(d, dict):
                for k, v in d.items():
                    new_key = f"{parent_key}.{k}" if parent_key else k
                    items.extend(flatten(v, new_key))
            else:
                items.append((parent_key, clean_value(d)))
            return items

        flat_header = flatten(header)
        
        self.meta_table.setRowCount(len(flat_header))
        for row, (key, value) in enumerate(flat_header):
            self.meta_table.setItem(row, 0, QTableWidgetItem(key))
            self.meta_table.setItem(row, 1, QTableWidgetItem(value))

    def show_meta_detail(self, row, column):
        """Shows a popup with the full text of the selected metadata."""
        key_item = self.meta_table.item(row, 0)
        val_item = self.meta_table.item(row, 1)
        if key_item and val_item:
            QMessageBox.information(self, "Metadata Detail", 
                                    f"<b>Property:</b> {key_item.text()}<br><br>"
                                    f"<b>Value:</b> {val_item.text()}")

    def on_selection_changed(self):
        self.plot_btn.setEnabled(len(self.sweep_listbox.selectedItems()) > 0)

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
            else:
                unit_label = "Time (s)"

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
