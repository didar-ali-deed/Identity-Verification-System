"""Run actual OCR against the two explicitly fictional specimen images."""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from app.services.ocr_service import extract_text, get_raw_text, parse_document

parser = argparse.ArgumentParser()
parser.add_argument("--samples", default="/tmp/idv-samples")
parser.add_argument("--output", default="/tmp/synthetic-ocr-results.json")
args = parser.parse_args()
expected = {"full_name": "ALEX SAMPLE", "father_name": "JAMIE SAMPLE", "dob": "01.02.1990",
            "expiry_date": "01.01.2034", "gender": "Male", "nationality": "PAKISTANI",
            "national_id_number": "00000-0000000-0"}
report = {"scope": "Two generated, conspicuously marked synthetic images; not an accuracy benchmark", "documents": []}
for kind, filename in [("national_id", "synthetic-cnic.png"), ("passport", "synthetic-passport.png")]:
    path = str(Path(args.samples) / filename)
    started = time.monotonic()
    print(f"Running actual OCR: {kind}", flush=True)
    try:
        rows = extract_text(path)
        fields = parse_document(get_raw_text(rows), rows, kind, image_path=path)
        result = {"document_type": kind, "seconds": round(time.monotonic() - started, 2), "ocr_rows": rows,
                  "fields": fields, "expected": expected}
        report["documents"].append(result)
        print(json.dumps({"document_type": kind, "seconds": result["seconds"], "fields": fields}, indent=2), flush=True)
    except Exception as exc:
        report["documents"].append({"document_type": kind, "error": f"{type(exc).__name__}: {exc}"})
        print(f"Failed: {kind}: {exc}", flush=True)
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf8")
