import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

modules = ['app.main', 'app.tasks', 'torch', 'torchvision', 'easyocr', 'mediapipe', 'deepface.DeepFace']
failures = []
for name in modules:
    try:
        importlib.import_module(name)
        if name == 'mediapipe':
            import mediapipe as mp
            import numpy as np
            from mediapipe.tasks.python.vision import FaceDetector
            mp.Image(image_format=mp.ImageFormat.SRGB, data=np.zeros((8, 8, 3), dtype=np.uint8))
        print(f'OK: {name}')
    except Exception as exc:
        failures.append(name)
        print(f'FAILED: {name}: {type(exc).__name__}: {exc}')
if failures:
    sys.exit(1)
