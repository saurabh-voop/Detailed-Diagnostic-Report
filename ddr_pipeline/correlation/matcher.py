"""
Stage 2: Correlation Engine
Uses Gemini vision to match thermal visible-light photos to inspection report photos,
building a mapping: thermal_page -> inspection_photo_number -> impacted_area
"""

import google.generativeai as genai
import json
import os
import time
from PIL import Image

BATCH_SIZE = 15  # inspection photos per Gemini call (stays within token limits)


def build_correlation_map(
    thermal_pages: list,
    inspection_data: dict,
    api_key: str,
    model_name: str = "gemini-1.5-flash"
) -> list:
    """
    For each thermal page, find which inspection report photo its visible-light
    photo matches, then map to the corresponding impacted area.

    Returns enriched thermal_pages list with correlation data added.
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    impacted_areas = inspection_data["impacted_areas"]
    inspection_photos = inspection_data["photos"]

    # Build lookup: photo_number -> area info
    photo_to_area = {}
    for area in impacted_areas:
        for photo_num in area.get("negative_photos", []):
            photo_to_area[photo_num] = {
                "area_id": area["area_id"],
                "description": area["negative_description"],
                "side": "negative"
            }
        for photo_num in area.get("positive_photos", []):
            photo_to_area[photo_num] = {
                "area_id": area["area_id"],
                "description": area["positive_description"],
                "side": "positive"
            }

    print(f"\nStarting correlation for {len(thermal_pages)} thermal pages...")

    enriched_pages = []
    for i, thermal_page in enumerate(thermal_pages):
        print(f"  Correlating thermal page {i+1}/{len(thermal_pages)}...")

        correlation = _correlate_single_page(
            thermal_page=thermal_page,
            inspection_photos=inspection_photos,
            photo_to_area=photo_to_area,
            model=model,
            page_index=i
        )

        thermal_page["correlation"] = correlation
        enriched_pages.append(thermal_page)

        # Rate limiting: 4s between pages (Gemini Flash free tier = 15 RPM)
        if i < len(thermal_pages) - 1:
            time.sleep(4)

    return enriched_pages


def _correlate_single_page(
    thermal_page: dict,
    inspection_photos: dict,
    photo_to_area: dict,
    model,
    page_index: int
) -> dict:
    """
    Use Gemini vision to match a thermal page's visible-light photo
    to the most similar inspection photo, searching in batches of BATCH_SIZE.
    Returns the best match found across all batches.
    """
    visible_path = thermal_page.get("visible_image_path")

    if not visible_path or not os.path.exists(visible_path):
        return {
            "matched_photo": None,
            "area_id": None,
            "confidence": "low",
            "reason": "Visible image file not found"
        }

    try:
        thermal_visible_img = Image.open(visible_path)
    except Exception as e:
        return {
            "matched_photo": None,
            "area_id": None,
            "confidence": "low",
            "reason": f"Could not load visible image: {e}"
        }

    photo_numbers = sorted(inspection_photos.keys())
    batches = [
        photo_numbers[i:i + BATCH_SIZE]
        for i in range(0, len(photo_numbers), BATCH_SIZE)
    ]

    best = {
        "matched_photo": None,
        "area_id": None,
        "confidence": "low",
        "reason": "No match found across all batches"
    }

    for batch_nums in batches:
        result = _correlate_batch(
            thermal_visible_img=thermal_visible_img,
            batch_photo_nums=batch_nums,
            inspection_photos=inspection_photos,
            photo_to_area=photo_to_area,
            model=model,
            page_index=page_index,
            filename=thermal_page.get("filename", "unknown")
        )

        # Stop early on high-confidence match; otherwise keep best so far
        if result["confidence"] == "high":
            return result
        if result["confidence"] == "medium" and best["confidence"] != "high":
            best = result
        elif result["matched_photo"] and best["confidence"] == "low":
            best = result

        # Brief pause between batches to respect rate limits
        time.sleep(2)

    return best


def _correlate_batch(
    thermal_visible_img: Image.Image,
    batch_photo_nums: list,
    inspection_photos: dict,
    photo_to_area: dict,
    model,
    page_index: int,
    filename: str
) -> dict:
    """
    Run one Gemini call comparing the thermal visible photo against a batch
    of inspection photos. Returns the best match within this batch.
    """
    content_parts = []

    intro = (
        f"You are analyzing building inspection photos to find matching images.\n\n"
        f"I will show you:\n"
        f"1. A VISIBLE LIGHT PHOTO from a thermal inspection camera\n"
        f"2. Numbered INSPECTION PHOTOS from the formal inspection report\n\n"
        f"Your task: Find which inspection photo number BEST matches the visible light photo.\n"
        f"They show the same physical location from similar angles.\n"
        f"Look for: same wall/floor/ceiling area, same damage patterns, same fixtures, same room features.\n\n"
        f"THERMAL REPORT VISIBLE PHOTO (Page {page_index + 1}, filename: {filename}):"
    )
    content_parts.append(intro)
    content_parts.append(thermal_visible_img)
    content_parts.append("\n\nINSPECTION REPORT PHOTOS FOR COMPARISON:")

    valid_photos = []
    for photo_num in batch_photo_nums:
        photo_path = inspection_photos.get(photo_num)
        if photo_path and os.path.exists(photo_path):
            try:
                insp_img = Image.open(photo_path)
                content_parts.append(f"\nPhoto {photo_num}:")
                content_parts.append(insp_img)
                valid_photos.append(photo_num)
            except Exception:
                pass

    if not valid_photos:
        return {
            "matched_photo": None,
            "area_id": None,
            "confidence": "low",
            "reason": "No valid inspection photos in this batch"
        }

    content_parts.append(
        f"\n\nINSTRUCTIONS:\n"
        f"- Compare the thermal visible photo with all inspection photos above\n"
        f"- Find the BEST MATCH based on visual similarity (same location, same features)\n"
        f"- If no good match exists in this set, say so honestly\n\n"
        f"Respond ONLY with valid JSON in this exact format:\n"
        f'{{\n'
        f'  "matched_photo_number": <integer or null>,\n'
        f'  "confidence": "high" | "medium" | "low",\n'
        f'  "visual_match_reason": "<brief explanation of what features matched>",\n'
        f'  "alternative_matches": [<photo numbers that also look similar>]\n'
        f'}}'
    )

    try:
        response = model.generate_content(content_parts)
        response_text = response.text.strip()

        # Strip markdown code fences if present
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        result = json.loads(response_text)

        matched_num = result.get("matched_photo_number")
        area_info = photo_to_area.get(matched_num, {}) if matched_num else {}

        return {
            "matched_photo": matched_num,
            "area_id": area_info.get("area_id"),
            "area_description": area_info.get("description", "Not Available"),
            "side": area_info.get("side", "unknown"),
            "confidence": result.get("confidence", "low"),
            "reason": result.get("visual_match_reason", ""),
            "alternative_matches": result.get("alternative_matches", [])
        }

    except json.JSONDecodeError as e:
        print(f"    JSON parse error for page {page_index+1}: {e}")
        return {
            "matched_photo": None,
            "area_id": None,
            "confidence": "low",
            "reason": f"Could not parse model response: {str(e)}"
        }
    except Exception as e:
        print(f"    API error for page {page_index+1}: {e}")
        return {
            "matched_photo": None,
            "area_id": None,
            "confidence": "low",
            "reason": f"API error: {str(e)}"
        }


def group_by_area(enriched_thermal_pages: list) -> dict:
    """
    Group enriched thermal pages by their matched impacted area.
    Returns: {area_id: [thermal_page, ...]}
    """
    area_groups = {}
    unmatched = []

    for page in enriched_thermal_pages:
        correlation = page.get("correlation", {})
        area_id = correlation.get("area_id")

        if area_id is not None:
            if area_id not in area_groups:
                area_groups[area_id] = []
            area_groups[area_id].append(page)
        else:
            unmatched.append(page)

    if unmatched:
        area_groups["unmatched"] = unmatched

    return area_groups
