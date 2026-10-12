---
title: "NeuralPilot — Hand-Gesture Steering Control with Computer Vision (macOS)"
slug: "neuralpilot"
kind: "project"
site_slug: null
page_url: "https://github.com/adityamukhopadhyay/NeuralPilot"
source: "public GitHub repository adityamukhopadhyay/NeuralPilot (MIT licence), read 2026-10-08; personal project, December 2024"
summary: "A personal computer-vision project: a webcam-based virtual steering wheel. MediaPipe Hands tracks both hands in real time, OpenCV draws the wheel and computes the steering angle from the two wrist positions, and the angle is converted into WASD key presses on macOS through the Quartz event API so any driving game can be steered by hand gestures."
---
# NeuralPilot — Hand-Gesture Steering Control with Computer Vision (macOS)

## 1. Summary

NeuralPilot is a personal computer-vision project by Aditya Mukhopadhyay, written in Python in December 2024 and published on GitHub under the MIT licence (github.com/adityamukhopadhyay/NeuralPilot). It turns a laptop webcam into a virtual steering wheel: the program tracks the user's hands in real time, works out the angle between them, and converts that into keyboard commands (W, A, S, D), so a driving game that expects keyboard input can be steered with hand gestures. It was built and optimised for an Apple Silicon (M1) MacBook.

It is a side project, not production work and not part of Aditya's resume. It is useful as evidence of hands-on computer-vision experience: real-time landmark detection, frame-by-frame geometry, and a low-latency control loop.

## 2. Tech Stack

- Language: Python 3.10+.
- Hand tracking: MediaPipe Hands (Google's on-device hand landmark model), run with `model_complexity=0`, the lightweight model, so the loop stays real-time on an M1 CPU; detection and tracking confidence thresholds of 0.5.
- Image capture and drawing: OpenCV (`cv2`), webcam capture at 1280×720, drawing of landmarks, the wheel and on-screen text.
- Numerics: NumPy for the text-overlay masking.
- Key simulation: the macOS Quartz framework through `pyobjc-framework-Quartz` (`CGEventCreateKeyboardEvent` posted to the HID event tap), using Carbon virtual key codes for W, A, S and D.
- No training and no custom model: the project uses MediaPipe's pre-trained hand landmark model as-is.

## 3. How It Works

### 3.1 Capture and detection loop
`neural_pilot.py` opens the default camera with OpenCV, and for every frame converts BGR to RGB, runs MediaPipe Hands, and converts back for drawing. The frame is marked read-only during inference (`image.flags.writeable = False`) to avoid a copy, a standard MediaPipe optimisation. The annotated frame is shown mirrored (`cv2.flip(image, 1)`) so the view behaves like a mirror for the user; pressing `q` exits.

### 3.2 From landmarks to a steering angle
For each detected hand, the code takes the WRIST landmark (landmark 0 of MediaPipe's 21-point hand model) and converts its normalised coordinates to pixel coordinates. The control logic depends on how many hands are visible:

- **Two hands:** the midpoint between the two wrists becomes the centre of a virtual steering wheel of radius 150 px. The angle of the line joining the wrists, `atan2(dy, dx)`, is the steering angle. The wheel (a circle plus the diameter line through both wrists, and a perpendicular indicator line) is drawn on the frame. Because the display is mirrored, the x-coordinates are flipped before computing the angle used for the decision, so that "turn left" on screen matches the user's physical motion.
- **One hand:** reverse mode.
- **No hands:** neutral, nothing is pressed.

### 3.3 Mapping the angle to key presses
A turning threshold of 30 degrees decides the action:

- `|angle| ≤ 30°` → keep straight: release S, A and D, hold W.
- `angle > 30°` → turn one way: release the other keys, hold A.
- `angle < −30°` → turn the other way: release the other keys, hold D.
- one hand visible → reverse: release W, A, D, hold S.

Key handling lives in `ai_controller.py` (`KeyController`): `press_key` and `release_key` create a Quartz keyboard event for the key's virtual key code and post it to the HID event tap, so the key press is seen by whatever application is in the foreground, exactly as if typed. Keys are held, not tapped, so the game sees continuous input while the gesture is held; every state change releases the keys of the previous state first, so two contradictory keys are never down at once.

### 3.4 Mirrored text overlay
Since the frame is displayed flipped, ordinary `cv2.putText` would render backwards. The project renders the status text ("Turn left", "Keep straight", "Reverse") onto a small temporary image, flips that image horizontally, builds a mask from the non-zero pixels, and composites it onto the frame with bounds-checked slicing, so the text reads correctly in the mirrored view.

## 4. Design Decisions and Limitations

- **Why wrists only:** using the two wrist points keeps the geometry trivial (one `atan2`) and robust; finger landmarks are drawn but not used for control.
- **Why a fixed 30° threshold:** a dead zone in the middle stops the wheel from oscillating between left and right when the hands are nearly level.
- **Why Quartz rather than a cross-platform library:** the project targets macOS specifically; posting CGEvents to the HID tap is the most reliable way to drive games that read raw key state. The README notes that other operating systems would need their own key-simulation layer.
- **Limitations:** macOS only; binary steering (left / straight / right) rather than proportional; W is always held while steering with two hands, so there is no coasting; no acceleration or brake gesture beyond reverse; depends on good lighting for hand detection.

## 5. What It Demonstrates

- Real-time computer vision on commodity hardware: a MediaPipe + OpenCV loop tuned for CPU inference on an M1.
- Converting landmark output into a control signal with simple, explainable geometry.
- OS-level integration from Python (Quartz event taps) to make the vision output actually useful.
- Small, readable code: two files (`neural_pilot.py` ≈ 200 lines, `ai_controller.py` ≈ 60 lines) and a four-line requirements file (opencv-python, mediapipe, numpy, pyobjc-framework-Quartz).
