Diagrams for TrackEneer report

This folder contains a small utility to programmatically generate flowchart PNGs used in the report.

Files
- `generate_diagrams.py`: Python script that uses python-graphviz to create four module flowcharts:
  - `trackeneer_scheduling_flowchart.png`
  - `study_module_flowchart.png`
  - `placement_module_flowchart.png`
  - `insights_module_flowchart.png`

Requirements
1. Install the Graphviz system package (required by the python graphviz library). On Windows, download and install from https://graphviz.org/download/ and make sure `dot.exe` is on your PATH.
2. Install the python package:

```powershell
pip install graphviz
```

Usage
```powershell
# generate large PNGs (300 DPI) into ./flowcharts
python generate_diagrams.py --format png --dpi 300

# generate scalable SVGs into ./flowcharts
python generate_diagrams.py --format svg

# generate only scheduling and study diagrams into a custom outdir
python generate_diagrams.py --modules scheduling,study --outdir ./flowcharts --format png --dpi 300
```

Notes
- The script writes files into the `flowcharts/` directory beside the script by default.
- Use `--format svg` to get vector outputs that scale without loss of quality (recommended for Overleaf/PDF).
- For raster PNGs, increase `--dpi` (e.g., 300) to produce high-resolution images suitable for large full-page embedding.
- If you need different styling or want to add nodes/edges, edit `generate_diagrams.py` accordingly.
