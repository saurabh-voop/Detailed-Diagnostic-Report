"""
Stage 2: Correlation Engine
Uses GPT-4o-mini vision to match thermal visible-light photos to inspection report photos,
building a mapping: thermal_page -> inspection_photo_number -> impacted_area
"""

import base64
import io
import json
import os
import re
import time
from PIL import Image
from openai import OpenAI, RateLimitError

BATCH_SIZE = 15  # inspection photos per API call (stays within token limits)
MAX_RETRIES = 3
DEFAULT_RETRY_WAIT = 60


def _img_to_b64(path: str):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8"), mime


def _pil_to_b64(img: Image.Image):
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8"), "image/jpeg"


def build_correlation_map(
    thermal_pages: list,
    inspection_data: dict,
    api_key: str,
    model_name: str = "gpt-4o-mini"
) -> list:
    """
    For each thermal page, find which inspection report photo its visible-light
    photo matches, then map to the corresponding impacted area.

    Returns enriched thermal_pages list with correlation data added.
    """
    client = OpenAI(api_key=api_key)

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
            client=client,
            model_name=model_name,
            page_index=i
        )

        thermal_page["correlation"] = correlation
        enriched_pages.append(thermal_page)

        if i < len(thermal_pages) - 1:
            time.sleep(2)

    return enriched_pages


def _correlate_single_page(
    thermal_page: dict,
    inspection_photos: dict,
    photo_to_area: dict,
    client,
    model_name: str,
    page_index: int
) -> dict:
    """
    Use GPT-4o-mini vision to match a thermal page's visible-light photo
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
            client=client,
            model_name=model_name,
            page_index=page_index,
            filename=thermal_page.get("filename", "unknown")
        )

        if result["confidence"] == "high":
            return result
        if result["confidence"] == "medium" and best["confidence"] != "high":
            best = result
        elif result["matched_photo"] and best["confidence"] == "low":
            best = result

        time.sleep(3)

    return best


def _correlate_batch(
    thermal_visible_img: Image.Image,
    batch_photo_nums: list,
    inspection_photos: dict,
    photo_to_area: dict,
    client,
    model_name: str,
    page_index: int,
    filename: str
) -> dict:
    """
    Run one GPT-4o-mini call comparing the thermal visible photo against a batch
    of inspection photos. Returns the best match within this batch.
    """
    try:
        b64_thermal, mime_thermal = _pil_to_b64(thermal_visible_img)
    except Exception as e:
        return {
            "matched_photo": None,
            "area_id": None,
            "confidence": "low",
            "reason": f"Could not encode thermal image: {e}"
        }

    content = [
        {
            "type": "text",
            "text": (
                f"You are analyzing building inspection photos to find matching images.\n\n"
                f"I will show you:\n"
                f"1. A VISIBLE LIGHT PHOTO from a thermal inspection camera\n"
                f"2. Numbered INSPECTION PHOTOS from the formal inspection report\n\n"
                f"Your task: Find which inspection photo number BEST matches the visible light photo.\n"
                f"They show the same physical location from similar angles.\n"
                f"Look for: same wall/floor/ceiling area, same damage patterns, same fixtures, same room features.\n\n"
                f"THERMAL REPORT VISIBLE PHOTO (Page {page_index + 1}, filename: {filename}):"
            )
        },
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_thermal};base64,{b64_thermal}",
                "detail": "low"
            }
        },
        {
            "type": "text",
            "text": "\n\nINSPECTION REPORT PHOTOS FOR COMPARISON:"
        }
    ]

    valid_photos = []
    for photo_num in batch_photo_nums:
        photo_path = inspection_photos.get(photo_num)
        if photo_path and os.path.exists(photo_path):
            try:
                b64_insp, mime_insp = _img_to_b64(photo_path)
                content.append({"type": "text", "text": f"\nPhoto {photo_num}:"})
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_insp};base64,{b64_insp}",
                        "detail": "low"
                    }
                })
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

    content.append({
        "type": "text",
        "text": (
            f"\n\nINSTRUCTIONS:\n"
            f"- Compare the thermal visible photo with all inspection photos above\n"
            f"- Find the BEST MATCH based on visual similarity (same location, same features)\n"
            f"- If no good match exists in this set, say so honestly\n\n"
            f"Respond ONLY with valid JSON in this exact format:\n"
            '{{\n'
            '  "matched_photo_number": <integer or null>,\n'
            '  "confidence": "high" | "medium" | "low",\n'
            '  "visual_match_reason": "<brief explanation of what features matched>",\n'
            '  "alternative_matches": [<photo numbers that also look similar>]\n'
            '}}'
        )
    })

    return _call_with_retry(
        client=client,
        model_name=model_name,
        content=content,
        photo_to_area=photo_to_area,
        page_index=page_index
    )


def _call_with_retry(
    client,
    model_name: str,
    content: list,
    photo_to_area: dict,
    page_index: int
) -> dict:
    """
    Call OpenAI chat completions with automatic retry on rate limit errors.
    """
    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": content}],
                response_format={"type": "json_object"},
                max_tokens=300
            )
            response_text = response.choices[0].message.content.strip()
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
                "reason": f"Could not parse model response: {e}"
            }

        except RateLimitError as e:
            retry_after = getattr(e, "retry_after", None)
            wait = (int(retry_after) + 5) if retry_after else DEFAULT_RETRY_WAIT
            if attempt < MAX_RETRIES - 1:
                print(f"    Rate limited. Waiting {wait}s before retry {attempt + 2}/{MAX_RETRIES}...")
                time.sleep(wait)
            else:
                return {
                    "matched_photo": None,
                    "area_id": None,
                    "confidence": "low",
                    "reason": f"Rate limit exceeded after {MAX_RETRIES} retries"
                }

        except Exception as e:
            err = str(e)
            if "429" in err and attempt < MAX_RETRIES - 1:
                delay_match = re.search(r'retry[_\-]after[:\s]+(\d+)', err, re.IGNORECASE)
                wait = int(delay_match.group(1)) + 5 if delay_match else DEFAULT_RETRY_WAIT
                print(f"    Rate limited (429). Waiting {wait}s before retry {attempt + 2}/{MAX_RETRIES}...")
                time.sleep(wait)
            else:
                print(f"    API error for page {page_index+1}: {err[:120]}")
                return {
                    "matched_photo": None,
                    "area_id": None,
                    "confidence": "low",
                    "reason": f"API error: {err[:120]}"
                }

    return {
        "matched_photo": None,
        "area_id": None,
        "confidence": "low",
        "reason": "All retries exhausted"
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
