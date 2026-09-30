# Synthetic OCR specimens

The two PNGs depict fictional Alex Sample, use conspicuous specimen markings and invalid identity numbers, and are for OCR smoke checks only. They cannot establish verification accuracy or serve as authentic documents.

EasyOCR is the sole OCR provider. Superseded TrOCR reports were removed to avoid presenting obsolete results as current evaluation. Keep new reports limited to these synthetic specimens.

```powershell
docker cp docs/samples identity-verification-system-celery-worker-1:/tmp/idv-samples
docker cp scripts/check_synthetic_ocr.py identity-verification-system-celery-worker-1:/tmp/check_synthetic_ocr.py
docker compose exec -T celery-worker python /tmp/check_synthetic_ocr.py
```

The report is written inside the container at `/tmp/synthetic-ocr-results.json`. Missing or incorrect fields are actual model limitations, not values to overwrite with the expected answer. The first run may download EasyOCR models.
