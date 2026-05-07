"""Quick MRZ extraction test without the API."""
import sys
from pathlib import Path

# Add src to path so we can import document_pipeline
sys.path.insert(0, str(Path(__file__).parent / "src"))

from document_pipeline.mrz import extract_passport_mrz

# Test file path
passport_pdf = Path("C:/Users/Universal/Documents/mufaddal/pdf filler/examples/passport-my.pdf")

if not passport_pdf.exists():
    print(f"File not found: {passport_pdf}")
    sys.exit(1)

try:
    result = extract_passport_mrz(passport_pdf.read_bytes())
    print("[OK] Extraction successful!")
    print(f"{'Field':<25} | {'Value'}")
    print("-" * 60)

    for field_name, value in result.model_dump().items():
        print(f"{field_name:<25} | {value}")

except Exception as e:
    print(f"[FAIL] Extraction failed: {e}")
    sys.exit(1)
