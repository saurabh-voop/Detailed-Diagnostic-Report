"""
Stage 1: Document Ingestion
Extracts text, metadata, and images from both PDFs.
"""

import fitz  # PyMuPDF
import os
import io
import re
from PIL import Image

# Matches known checklist answer values
_VALUE_RE = re.compile(
    r'^(Yes|No|All time|Moderate|N/A|Not sure|\d+%|Not Available)$',
    re.IGNORECASE
)


def extract_inspection_report(pdf_path: str, photos_dir: str) -> dict:
    """
    Extract all structured data from the inspection report PDF.
    Returns a dict with text sections, impacted areas, checklist, summary table.
    """
    doc = fitz.open(pdf_path)
    result = {
        "property_info": {},
        "impacted_areas": [],
        "checklist": {},
        "summary_table": [],
        "photos": {}  # photo_number -> file_path
    }

    # --- Classify pages by content keywords ---
    impacted_pages, checklist_pages, summary_pages = [], [], []

    for page_num in range(len(doc)):
        text = doc[page_num].get_text()
        if "Impacted Area" in text or "Negative side Description" in text:
            impacted_pages.append(page_num)
        if (
            "Inspection Checklists" in text
            or "Leakage during" in text
            or "Gaps around Nahani" in text
            or "Condition of cracks" in text
        ):
            checklist_pages.append(page_num)
        if "SUMMARY TABLE" in text:
            summary_pages.append(page_num)

    # --- Parse property info (page 1) ---
    result["property_info"] = _parse_property_info(doc[0].get_text())

    # --- Parse impacted areas ---
    impacted_text = "\n".join(doc[p].get_text() for p in impacted_pages)
    result["impacted_areas"] = _parse_impacted_areas(impacted_text)

    # --- Parse checklist ---
    checklist_text = "\n".join(doc[p].get_text() for p in checklist_pages)
    result["checklist"] = _parse_checklist(checklist_text)

    # --- Parse summary table ---
    summary_text = "\n".join(doc[p].get_text() for p in summary_pages)
    result["summary_table"] = _parse_summary_table(summary_text)

    # --- Extract appendix photos ---
    result["photos"] = _extract_inspection_photos(doc, photos_dir)

    doc.close()
    return result


def _parse_property_info(text: str) -> dict:
    info = {}
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # Fields: value may appear after a colon on same line, or on next line
    label_map = {
        "inspection_date": ["Inspection Date"],
        "inspected_by": ["Inspected By"],
        "property_type": ["Property Type"],
        "previous_structural_audit": ["Previous Structural audit", "Structural audit"],
        "previous_repair_work": ["Previous Repair work", "Repair work"],
        "impacted_rooms": ["Impacted Areas/Rooms", "Impacted Rooms", "Impacted Areas"],
    }
    for key, markers in label_map.items():
        info[key] = "Not Available"
        for i, line in enumerate(lines):
            if not any(m.lower() in line.lower() for m in markers):
                continue
            # Try inline "Label: Value"
            if ':' in line:
                val = line.split(':', 1)[1].strip()
                if val and not any(m.lower() in val.lower() for m in markers):
                    info[key] = val
                    break
            # Try next-line value
            if i + 1 < len(lines):
                val = lines[i + 1].strip().rstrip(':')
                if val and not any(m.lower() in val.lower() for m in markers):
                    info[key] = val
                    break

    # Score: first "XX.XX%" in page text
    score_match = re.search(r'(\d+\.?\d*)\s*%', text)
    info["score"] = float(score_match.group(1)) if score_match else "Not Available"

    # Floors: integer after "Floors"
    floors_match = re.search(r'Floors[:\s]+(\d+)', text, re.IGNORECASE)
    info["floors"] = int(floors_match.group(1)) if floors_match else "Not Available"

    # Flagged items
    flagged_match = re.search(r'Flagged\s+items?[:\s]+(\d+)', text, re.IGNORECASE)
    info["flagged_items"] = int(flagged_match.group(1)) if flagged_match else "Not Available"

    return info


def _extract_photo_numbers(text: str) -> list:
    """
    Extract photo numbers handling both individual references and ranges.
    Handles: "Photo 5", "Photos 59 to 64", "Photos 12-15"
    """
    numbers = set()
    # Range formats: "Photos N to M" or "Photos N-M"
    for m in re.finditer(r'Photos?\s+(\d+)\s+(?:to|-)\s+(\d+)', text, re.IGNORECASE):
        numbers.update(range(int(m.group(1)), int(m.group(2)) + 1))
    # Individual: "Photo N" (only if not already covered by a range)
    for m in re.finditer(r'Photo\s+(\d+)', text, re.IGNORECASE):
        numbers.add(int(m.group(1)))
    return sorted(numbers)


def _parse_impacted_areas(text: str) -> list:
    areas = []

    # Split on "Impacted Area N" headers, tolerating whitespace variations
    blocks = re.split(r'Impacted\s+Area\s+\d+', text, flags=re.IGNORECASE)

    for idx, block in enumerate(blocks[1:], start=1):
        area = {"area_id": idx}

        # Negative side description — value may follow on same line or next line
        neg_desc_m = re.search(
            r'Negative\s+side\s+Description\s*[:\n]\s*(.+?)'
            r'(?=Negative\s+side\s+photographs|Positive\s+side\s+Description|Impacted\s+Area|\Z)',
            block, re.DOTALL | re.IGNORECASE
        )
        area["negative_description"] = (
            neg_desc_m.group(1).strip().replace('\n', ' ')
            if neg_desc_m else "Not Available"
        )

        # Positive side description
        pos_desc_m = re.search(
            r'Positive\s+side\s+Description\s*[:\n]\s*(.+?)'
            r'(?=Positive\s+side\s+photographs|Impacted\s+Area|Site\s+Details|\Z)',
            block, re.DOTALL | re.IGNORECASE
        )
        area["positive_description"] = (
            pos_desc_m.group(1).strip().replace('\n', ' ')
            if pos_desc_m else "Not Available"
        )

        # Negative photos — extract from the negative-side block
        neg_block_m = re.search(
            r'Negative\s+side\s+photographs(.+?)'
            r'(?=Positive\s+side\s+Description|Impacted\s+Area|\Z)',
            block, re.DOTALL | re.IGNORECASE
        )
        area["negative_photos"] = (
            _extract_photo_numbers(neg_block_m.group(1))
            if neg_block_m else []
        )

        # Positive photos
        pos_block_m = re.search(
            r'Positive\s+side\s+photographs(.+?)(?=Impacted\s+Area|\Z)',
            block, re.DOTALL | re.IGNORECASE
        )
        area["positive_photos"] = (
            _extract_photo_numbers(pos_block_m.group(1))
            if pos_block_m else []
        )

        areas.append(area)

    return areas


def _parse_checklist(text: str) -> dict:
    result = {}
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    i = 0
    while i < len(lines):
        line = lines[i]
        # "Key\nValue" pattern — next line is a known answer
        if i + 1 < len(lines) and _VALUE_RE.match(lines[i + 1]):
            key = line.rstrip(':').strip()
            if key:
                result[key] = lines[i + 1].strip()
            i += 2
        elif ':' in line:
            # "Key: Value" on same line
            parts = line.split(':', 1)
            key, val = parts[0].strip(), parts[1].strip()
            if key and val and _VALUE_RE.match(val):
                result[key] = val
            i += 1
        else:
            i += 1
    return result


def _parse_summary_table(text: str) -> list:
    rows = {}

    # Each entry starts with a standalone integer (impacted) or N.M (exposed)
    # followed by description text until the next entry
    pattern = re.compile(
        r'(?m)^(\d+)(\.(\d+))?\s*\n((?:(?!^\d+\.?\d*\s*\n).)+)',
        re.DOTALL
    )
    for m in pattern.finditer(text):
        point_int = int(m.group(1))
        is_exposed = m.group(2) is not None  # has ".N" suffix
        description = ' '.join(m.group(4).split()).strip()
        if not description or len(description) < 10:
            continue
        if point_int not in rows:
            rows[point_int] = {
                "point": point_int,
                "impacted_area": "Not Available",
                "exposed_area": "Not Available"
            }
        if is_exposed:
            rows[point_int]["exposed_area"] = description
        else:
            rows[point_int]["impacted_area"] = description

    return sorted(rows.values(), key=lambda r: r["point"])


def _extract_inspection_photos(doc, photos_dir: str) -> dict:
    """
    Extract photos from appendix pages (detected dynamically).
    Skips banner/header images by aspect ratio (width > 4× height).
    Returns photo_number -> file_path mapping (sequential counter).
    """
    os.makedirs(photos_dir, exist_ok=True)
    photos = {}
    photo_counter = 1
    seen_xrefs = set()

    # Appendix pages: have "Photo N" labels but are NOT area description pages
    appendix_pages = [
        p for p in range(len(doc))
        if re.search(r'Photo\s+\d+', doc[p].get_text())
        and "Impacted Area" not in doc[p].get_text()
        and "Negative side" not in doc[p].get_text()
    ]

    for page_num in appendix_pages:
        page = doc[page_num]
        images = page.get_images(full=True)
        # Filter: real photos are roughly square-ish; banners are very wide
        real_photos = [
            img for img in images
            if img[2] > 200 and img[3] > 200
            and img[2] < img[3] * 4  # exclude wide banners
        ]

        for img in real_photos:
            xref = img[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            try:
                base_img = doc.extract_image(xref)
                save_path = os.path.join(
                    photos_dir, f"photo_{photo_counter:02d}.{base_img['ext']}"
                )
                with open(save_path, "wb") as f:
                    f.write(base_img["image"])
                photos[photo_counter] = save_path
                photo_counter += 1
            except Exception as e:
                print(f"  Warning: Could not extract photo xref {xref}: {e}")

    return photos


def extract_thermal_report(pdf_path: str, thermal_dir: str) -> list:
    """
    Extract all thermal pages as image pairs (thermal + visible).
    Returns list of dicts with metadata and image paths.
    """
    os.makedirs(thermal_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    thermal_pages = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()

        metadata = _parse_thermal_metadata(text, page_num)

        # Render full page at 2× resolution
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("jpeg")
        img = Image.open(io.BytesIO(img_data))
        w, h = img.size

        # Crop thermal image (upper-left content area)
        thermal_crop = img.crop((0, int(h * 0.08), int(w * 0.52), int(h * 0.52)))
        thermal_path = os.path.join(thermal_dir, f"thermal_page{page_num+1:02d}_thermal.jpg")
        thermal_crop.save(thermal_path, "JPEG", quality=90)

        # Crop visible-light photo (lower-left area)
        visible_crop = img.crop((0, int(h * 0.54), int(w * 0.45), h))
        visible_path = os.path.join(thermal_dir, f"thermal_page{page_num+1:02d}_visible.jpg")
        visible_crop.save(visible_path, "JPEG", quality=90)

        # Full page render for context
        full_path = os.path.join(thermal_dir, f"thermal_page{page_num+1:02d}_full.jpg")
        img.save(full_path, "JPEG", quality=85)

        metadata["thermal_image_path"] = thermal_path
        metadata["visible_image_path"] = visible_path
        metadata["full_page_path"] = full_path
        metadata["page_number"] = page_num + 1

        thermal_pages.append(metadata)
        print(f"  Processed thermal page {page_num+1}: {metadata.get('filename', 'unknown')}")

    doc.close()
    return thermal_pages


def _parse_thermal_metadata(text: str, page_num: int) -> dict:
    """
    Parse temperature readings and metadata from a thermal PDF page.

    The Bosch GTC camera PDF format places each label on its own line
    followed by the value on the next line, e.g.:
        Hotspot :
        28.8 °C          (° may render as replacement char �)
    We use a look-ahead approach instead of same-line matching.
    """
    metadata = {}
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    def _extract_number(s: str):
        m = re.search(r'(\d+\.?\d*)', s)
        return float(m.group(1)) if m else None

    i = 0
    while i < len(lines):
        line = lines[i]
        next_line = lines[i + 1] if i + 1 < len(lines) else ""

        if line.startswith("Hotspot"):
            val = _extract_number(next_line)
            if val is not None:
                metadata["hotspot_temp"] = val
            i += 2
        elif line.startswith("Coldspot"):
            val = _extract_number(next_line)
            if val is not None:
                metadata["coldspot_temp"] = val
            i += 2
        elif line.startswith("Emissivity"):
            val = _extract_number(next_line)
            if val is not None:
                metadata["emissivity"] = val
            i += 2
        elif line.startswith("Reflected"):
            val = _extract_number(next_line)
            if val is not None:
                metadata["reflected_temp"] = val
            i += 2
        elif "Thermal image" in line or (line.startswith("RB") and line.endswith(("X", "X.JPG"))):
            fname_m = re.search(r'(RB\d+X)', line, re.IGNORECASE)
            if fname_m:
                metadata["filename"] = fname_m.group(1)
            i += 1
        elif "Device" in line and ":" in line:
            parts = line.split(':', 1)
            if len(parts) == 2 and parts[1].strip():
                metadata["device"] = parts[1].strip()
            i += 1
        elif "Serial" in line and ":" in line:
            parts = line.split(':', 1)
            if len(parts) == 2 and parts[1].strip():
                metadata["serial_number"] = parts[1].strip()
            i += 1
        else:
            i += 1

    # Temperature delta: key indicator of moisture severity
    if "hotspot_temp" in metadata and "coldspot_temp" in metadata:
        metadata["temp_delta"] = round(
            metadata["hotspot_temp"] - metadata["coldspot_temp"], 1
        )

    # Date (format DD/MM/YY or DD/MM/YYYY)
    date_m = re.search(r'\d{2}/\d{2}/\d{2,4}', text)
    if date_m:
        metadata["date"] = date_m.group(0)

    return metadata
