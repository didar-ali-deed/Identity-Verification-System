# Model setup and licensing

The public `/demo` uses synthetic fixtures and needs no models, database, Redis or account.

## Default CPU development

The full Docker build installs CPU PyTorch, EasyOCR, MediaPipe and DeepFace. EasyOCR is the default document provider; its detector/recognizer models are cached under the mounted `/root/.cache/easyocr` directory. Models download on first real use. `INFERENCE_USE_GPU=false` is the default.

EasyOCR is the only OCR engine. Review and pipeline share its spatial visual-field parser; MRZ check digits remain independently validated. Provider confidence is uncalibrated, not measured accuracy. Low or missing confidence triggers review. Preview rotation controls and EXIF-aware preprocessing help with sideways images; always inspect the extracted text.

The default `LIVENESS_BACKEND=heuristic` is useful for exercising the workflow but does not permit automatic approval. For learned passive liveness, configure MiniFASNet below.

## Optional enhanced providers

Locally, from the repository root:

```powershell
.venv\Scripts\python.exe -m pip install -r backend\requirements-enhanced.txt
```

Set these in `backend/.env` for local Python development or root `.env` for Docker:

```dotenv
FACE_BACKEND=insightface
INSTALL_ENHANCED=true
```

`FACE_BACKEND=insightface` uses the `buffalo_l` model pack. Otherwise the default is MediaPipe detection and DeepFace Facenet comparison. OCR uses EasyOCR only; provider confidence still requires calibration against representative documents.

## MiniFASNet

The adapter follows the multi-frame approach in the separate KYC engine. The upstream source and weights are external artifacts and are excluded from Git and Docker build contexts.

```powershell
.\scripts\prepare_models.ps1
# If you already obtained trusted upstream weights:
.\scripts\prepare_models.ps1 -WeightsDirectory 'C:\path\to\weights'
```

The expected folder is `backend/third_party/Silent-Face-Anti-Spoofing/resources/anti_spoof_models`. Typical upstream filenames are `2.7_80x80_MiniFASNetV2.pth` and `4_0_0_80x80_MiniFASNetV1SE.pth`. Obtain weights from the [upstream project](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing), retain their provenance and use only trusted artifacts. PyTorch model loading may execute code from untrusted checkpoints.

Set `LIVENESS_BACKEND=minifasnet`. The camera UI captures three frames over one second. The server scores all submitted frames and requires every score to meet `LIVENESS_THRESHOLD` (default 0.75). Missing code, missing weights, inference errors, invalid outputs and fewer than three frames cannot approve an application.

Docker mounts `backend/third_party` into both the API and worker; local paths are relative to `backend`. No automatic switch to heuristic approval occurs when the learned model fails.

## Optional GPU

Use a driver-compatible CUDA wheel index from [PyTorch's installation guide](https://pytorch.org/get-started/locally/) for `TORCH_INDEX_URL`. Docker GPU use requires NVIDIA Container Toolkit. Enable `INFERENCE_USE_GPU=true` and run:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
```

For the InsightFace GPU provider, install `onnxruntime-gpu` instead of `onnxruntime` in your custom image or local environment. The supplied enhanced Docker image uses CPU ONNX Runtime; the GPU overlay assigns devices and enables CUDA PyTorch but does not substitute ONNX Runtime packages. Verify active providers and benchmark your chosen models before use.

## Licenses and evaluation

Application source uses the MIT license. Model weights have separate terms:

| Component | Licensing reference |
|---|---|
| InsightFace library and pretrained models | [Upstream license notice](https://github.com/deepinsight/insightface/tree/master/python-package): library code is MIT; supplied pretrained models are for non-commercial research. Obtain suitable rights before commercial deployment. |
| Silent-Face source | [Apache 2.0 license](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/blob/master/LICENSE); confirm the terms for your exact weights. |
| DeepFace and underlying face models | [Project](https://github.com/serengil/deepface); underlying models may have their own licenses. |

Automated tests exercise adapters using synthetic outputs. They do not establish real-world accuracy. Measure OCR field accuracy, face false-match/false-non-match rates and PAD performance on representative, consented data before choosing operational thresholds.
