# PyWaveSurfer GUI (Qt)

A high-performance, cross-platform GUI for viewing and plotting `.h5` electrophysiology traces exported from WaveSurfer. Built with Python 3.10, PyQt6, and Matplotlib.

## Features

- **HiDPI Support:** Crisp text and UI scaling on 4K/retina displays.
- **Multi-Channel Viewing:** Automatically plots each channel in a separate, vertically stacked subplot.
- **Linked X-Axes:** Zooming or panning on one channel synchronizes the view across all others.
- **Interactive Navigation:** Supports standard keyboard shortcuts (e.g., 'h' for Home, 'x' for X-only zoom).
- **Unit Toggle:** Easily switch X-axis units between Seconds (s) and Milliseconds (ms).
- **Publication Ready:** Clean aesthetics with removed spines and high-density grids.

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
Created by Gemini CLI under the guidance of Hsin-Wei Lu
