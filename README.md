# RoadGuard AI

A lightweight road-monitoring and maintenance **prototype**. It combines an explainable repair-priority queue with a map, citizen reports, repair-status tracking, road-health estimates, and a clearly labeled demo mode.

> The sample data is simulated. Image-processing candidates, confidence values, and deterioration estimates are not scientifically validated or safety-certified. Human verification is required.

## Run the Python + OpenCV edition

Install Python 3.10 or later, open a terminal in this folder, and run:

```bash
pip install -r requirements.txt
python app.py
```

On Windows, you can use:

```powershell
py -m pip install -r requirements.txt
py app.py
```

Open **http://localhost:5000**. Start in Demo Mode or choose **Switch to live** to use the camera attached to the computer running Python. The default detector is a simple OpenCV image-processing heuristic, not a trained pothole model. If a camera is unavailable, the app falls back to demo mode.

The app automatically creates `data/reports.json` with illustrative records on first launch. This file is ignored by Git because it can contain user-submitted locations and reports. It is not a production database and should not be exposed publicly.

## Standalone HTML edition

Open `standalone.html` in a browser. No Python installation is required. Reports are saved in browser local storage where available; data may be lost if browser storage is cleared.

The HTML edition supports a live browser camera **view only**; it does not perform live OpenCV detection. It analyzes uploaded images using a simple browser heuristic. Map tiles and chart libraries are loaded from CDNs; fallback displays are provided when unavailable.

## Features

- Simulated detections and clearly labeled demo data
- Camera feed and unverified image-analysis candidates
- Location-based reports, with optional browser GPS and demo-coordinate fallback
- Matching damage reports grouped within approximately 75 metres
- Explainable, editable priority inputs and a ranked repair queue
- Repair status, assignment, ETA, and activity history
- Driver-warning demonstration and road-segment health estimates
- Search, filtering, CSV export, and demo reset

## Priority formula

```text
40% severity + 20% traffic + 15% road importance
+ 10% sensitive location + 10% citizen reports + 5% damage age
```

Inputs are normalized to 0–100. Weights, defaults, and predictive risk inputs are prototype assumptions, not engineering standards.

## Tests

```bash
python -m unittest test_roadguard
```

## Repository contents

- `app.py`, `detector.py`, `priority.py`, `database.py` — Python application
- `templates/`, `static/` — dashboard interface and demo road image
- `standalone.html` — browser-only edition
- `media/roadguard-reel.mp4` — 15-second promotional reel
- `PITCH_NOTES.md` — presentation and demo notes
- `test_roadguard.py` — regression tests

A compatible local YOLO model can optionally be supplied using the `ROADGUARD_MODEL` environment variable if `ultralytics` is installed separately. No model is included or automatically downloaded.
