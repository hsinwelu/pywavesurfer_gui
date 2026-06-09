# PyWaveSurfer GUI (Qt)

A high-performance, cross-platform GUI for viewing, plotting, and filtering `.h5` electrophysiology traces exported from WaveSurfer. Built with Python 3.10, PyQt6, Matplotlib, and SciPy.

## Features

### Browsing & loading
- **Folder browser** (left panel): pick a folder once and the tree shows only `.h5` files. Single-click a file to load it and auto-plot the first sweep; double-click a folder to re-root the tree. The last-used folder is remembered between sessions.
- **Sweep list**: single-click any sweep to plot it. Filter settings carry over so you can browse through sweeps under the same processing pipeline.
- **File metadata viewer**: hierarchical tree of the HDF5 header in a separate window. Double-click any leaf to see its full dotted path and value.

### Plot
- **HiDPI support**: crisp text and UI scaling on 4K / retina displays.
- **Multi-channel viewing**: each channel in its own vertically stacked subplot, with linked X-axes for synchronized zoom and pan.
- **X-axis unit toggle**: switch between seconds and milliseconds in place — the current zoom is preserved, no replot.
- **Zoom-preserving renders**: applying filters or toggling them on / off preserves your current `xlim` / `ylim`; pressing **Home** in the toolbar returns to the full auto-scaled view of the displayed data.
- **Interactive navigation**: standard matplotlib toolbar plus keyboard shortcuts.
- **Publication-ready aesthetics**: hidden top / right spines and light grids.

### Filters (right panel)
- **Zero-phase filtering** throughout — IIR families use `sosfiltfilt`, FIR uses `filtfilt` — so phase is preserved and there is no group delay.
- **Filter types**: low-pass, high-pass, band-pass, and notch (`scipy.signal.iirnotch` for mains hum).
- **Five filter families** for LP / HP / BP: Butterworth, Bessel, Chebyshev II, Elliptic, and FIR (`firwin` + `filtfilt`).
- **Per-channel selection**: a checkbox per channel decides which channels get filtered.
- **Filter ON / OFF toggle**: one-click switch between filtered and raw view. Any change to a filter parameter (family, order, FIR taps, cutoffs, channel selection, notch Q) live-updates the plot while the toggle is on.
- **In-app help windows** (the **?** buttons): plain-language explanations of every filter family and of the IIR-order / FIR-taps knobs, with **intracellular and juxtacellular recipes** (AP waveform, subthreshold PSPs, voltage-clamp EPSCs, juxtacellular spike detection, mains hum) and a callout for **fast-membrane neurons** (octopus cells, MSO) recommending a low-pass cutoff above 5 kHz.

## Prerequisites

- **Python:** 3.10 (Exactly 3.10 is recommended for maximum stability).
- **System Libraries (Linux only):** 
  ```bash
  sudo dnf install libxcb xcb-util-cursor xcb-util-wm xcb-util-keysyms xcb-util-renderutil
  ```

## Installation

1. **Clone the repository or download the files.**
2. **Create and activate a Conda environment (Recommended):**
   ```bash
   conda create -n wavesurfer python=3.10
   conda activate wavesurfer
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the GUI using Python:
```bash
python pywavesurfer_gui_qt.py
```

### Workflow at a glance

1. Click **Choose Folder** (top-left) to point the tree at your data directory. Double-click any folder in the tree to descend into it; press **↑ Up** to climb one level.
2. **Single-click** an `.h5` file in the tree — it loads, populates the sweep list, and plots the first sweep automatically.
3. **Single-click** any sweep name in the list to plot it.
4. Open **Show File Metadata** for the hierarchical header viewer.
5. On the right, configure the filter panel and click the **Filter: OFF** button to toggle it **ON** — the plot updates live as you change any parameter. Toggle **OFF** to compare against the raw trace.

### Keyboard Shortcuts
- **h**: Home (Reset zoom/pan)
- **p**: Pan mode
- **o**: Zoom-to-rectangle mode
- **x (Hold while zooming)**: Constrain zoom to X-axis only
- **g**: Toggle grid

## Creating a Standalone Executable (One-Click Version)

You can bundle the application into a single executable file that doesn't require Python to be installed on the target machine.

### 1. Install PyInstaller
```bash
pip install pyinstaller
```

### 2. Build the Executable
Run this command on the operating system you want to target (Windows, macOS, or Linux):

```bash
pyinstaller --onefile --windowed pywavesurfer_gui_qt.py
```

### 3. Retrieve the File
The finished executable will be located in the `dist/` folder:
- **Windows:** `dist/pywavesurfer_gui_qt.exe`
- **macOS:** `dist/pywavesurfer_gui_qt.app`
- **Linux:** `dist/pywavesurfer_gui_qt`

## License
MIT

---
Authors: Hsin-Wei Lu, with code contributions from Gemini CLI (initial scaffold) and Claude (Anthropic) (folder browser, metadata tree viewer, filter panel, and in-app help system).
