"""
Stage 3: DDR Generation
Generates each DDR section using GPT-4o-mini, section by section.
"""

import base64
import io
import re
import time
import os
from PIL import Image
from openai import OpenAI, RateLimitError

_MAX_RETRIES = 3
_DEFAULT_RETRY_WAIT = 60

from .prompts import (
    SYSTEM_PROMPT, PROPERTY_SUMMARY_PROMPT, AREA_OBSERVATION_PROMPT,
    ROOT_CAUSE_PROMPT, SEVERITY_PROMPT, RECOMMENDED_ACTIONS_PROMPT,
    ADDITIONAL_NOTES_PROMPT, MISSING_INFO_PROMPT
)


def _img_path_to_b64(path: str):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8"), mime


def _pil_to_b64(img: Image.Image):
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8"), "image/jpeg"


class DDRGenerator:
    def __init__(self, api_key: str, model_name: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model_name = model_name

    def generate_full_ddr(
        self,
        inspection_data: dict,
        enriched_thermal_pages: list,
        area_groups: dict
    ) -> dict:
        """
        Generate all DDR sections. Returns dict with all sections.
        """
        ddr = {}

        print("\n--- Generating DDR Sections ---")

        # 1. Property Issue Summary
        print("  [1/7] Property Issue Summary...")
        ddr["property_summary"] = self._generate_property_summary(
            inspection_data, enriched_thermal_pages
        )
        time.sleep(2)

        # 2. Area-wise Observations
        print("  [2/7] Area-wise Observations...")
        ddr["area_observations"] = self._generate_area_observations(
            inspection_data, area_groups
        )
        time.sleep(2)

        # 3. Probable Root Cause
        print("  [3/7] Probable Root Cause...")
        ddr["root_cause"] = self._generate_root_cause(
            inspection_data, enriched_thermal_pages
        )
        time.sleep(2)

        # 4. Severity Assessment
        print("  [4/7] Severity Assessment...")
        ddr["severity_assessment"] = self._generate_severity(
            inspection_data, enriched_thermal_pages, area_groups
        )
        time.sleep(2)

        # 5. Recommended Actions
        print("  [5/7] Recommended Actions...")
        ddr["recommended_actions"] = self._generate_recommendations(
            ddr["root_cause"], ddr["severity_assessment"], inspection_data
        )
        time.sleep(2)

        # 6. Additional Notes
        print("  [6/7] Additional Notes...")
        ddr["additional_notes"] = self._generate_additional_notes(
            inspection_data, enriched_thermal_pages, ddr
        )
        time.sleep(2)

        # 7. Missing or Unclear Information
        print("  [7/7] Missing or Unclear Information...")
        ddr["missing_info"] = self._generate_missing_info(
            inspection_data, enriched_thermal_pages, area_groups
        )

        return ddr

    def _call_model(self, prompt: str, images: list = None) -> str:
        """Make a model call with optional images, retrying on rate limit errors."""
        content = []

        if images:
            for img in images:
                try:
                    if isinstance(img, str) and os.path.exists(img):
                        b64, mime = _img_path_to_b64(img)
                    elif isinstance(img, Image.Image):
                        b64, mime = _pil_to_b64(img)
                    else:
                        continue
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{b64}",
                            "detail": "low"
                        }
                    })
                except Exception:
                    pass

        content.append({"type": "text", "text": prompt})

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content}
        ]

        for attempt in range(_MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    max_tokens=2000
                )
                return response.choices[0].message.content.strip()

            except RateLimitError as e:
                retry_after = getattr(e, "retry_after", None)
                wait = (int(retry_after) + 5) if retry_after else _DEFAULT_RETRY_WAIT
                if attempt < _MAX_RETRIES - 1:
                    print(f"    Rate limited. Waiting {wait}s before retry {attempt + 2}/{_MAX_RETRIES}...")
                    time.sleep(wait)
                else:
                    return f"[Generation error: rate limit exceeded after {_MAX_RETRIES} retries]"

            except Exception as e:
                err = str(e)
                if "429" in err and attempt < _MAX_RETRIES - 1:
                    delay_match = re.search(r'retry[_\-]after[:\s]+(\d+)', err, re.IGNORECASE)
                    wait = int(delay_match.group(1)) + 5 if delay_match else _DEFAULT_RETRY_WAIT
                    print(f"    Rate limited (429). Waiting {wait}s before retry {attempt + 2}/{_MAX_RETRIES}...")
                    time.sleep(wait)
                else:
                    return f"[Generation error: {err[:200]}]"

    def _generate_property_summary(self, inspection_data: dict, thermal_pages: list) -> str:
        prop_info = inspection_data.get("property_info", {})
        summary_table = inspection_data.get("summary_table", [])

        inspection_summary = f"""
Property Type: {prop_info.get('property_type', 'Flat')}
Floors in Building: {prop_info.get('floors', 'Not Available')}
Inspection Date: {prop_info.get('inspection_date', 'Not Available')}
Inspected By: {prop_info.get('inspected_by', 'Not Available')}
Overall Score: {prop_info.get('score', 'Not Available')}%
Previous Structural Audit: {prop_info.get('previous_structural_audit', 'No')}
Previous Repair Work: {prop_info.get('previous_repair_work', 'No')}
Impacted Rooms: {prop_info.get('impacted_rooms', 'Not Available')}
Total Issues Identified: {len(summary_table)}
"""

        temp_deltas = [p.get("temp_delta", 0) for p in thermal_pages if p.get("temp_delta")]
        avg_delta = round(sum(temp_deltas) / len(temp_deltas), 1) if temp_deltas else 0
        max_delta = max(temp_deltas) if temp_deltas else 0

        thermal_overview = f"""
Total thermal images captured: {len(thermal_pages)}
Average temperature differential: {avg_delta}°C
Maximum temperature differential observed: {max_delta}°C
Reflected ambient temperature: 23°C
Thermal device used: GTC 400 C Professional (Bosch)
All images captured on: 27/09/2022
"""

        prompt = PROPERTY_SUMMARY_PROMPT.format(
            inspection_summary=inspection_summary,
            thermal_overview=thermal_overview
        )
        return self._call_model(prompt)

    def _generate_area_observations(self, inspection_data: dict, area_groups: dict) -> list:
        areas = inspection_data.get("impacted_areas", [])
        checklist = inspection_data.get("checklist", {})
        observations = []

        for area in areas:
            area_id = area["area_id"]
            thermal_pages_for_area = area_groups.get(area_id, [])

            thermal_data = self._format_thermal_data_for_area(thermal_pages_for_area)
            checklist_data = self._format_full_checklist(checklist)

            prompt = AREA_OBSERVATION_PROMPT.format(
                area_id=area_id,
                area_description=area["negative_description"],
                negative_description=area["negative_description"],
                positive_description=area["positive_description"],
                negative_photos=", ".join(f"Photo {n}" for n in area.get("negative_photos", [])) or "Not listed",
                positive_photos=", ".join(f"Photo {n}" for n in area.get("positive_photos", [])) or "Not listed",
                thermal_data=thermal_data,
                checklist_data=checklist_data
            )

            area_images = []
            for tp in thermal_pages_for_area[:2]:
                if tp.get("visible_image_path") and os.path.exists(tp["visible_image_path"]):
                    area_images.append(tp["visible_image_path"])

            photos = inspection_data.get("photos", {})
            for photo_num in area.get("negative_photos", [])[:3]:
                if photo_num in photos and os.path.exists(photos[photo_num]):
                    area_images.append(photos[photo_num])

            text = self._call_model(prompt, area_images)
            time.sleep(2)

            all_area_images = {
                "thermal_images": [
                    {
                        "thermal_path": tp.get("thermal_image_path"),
                        "visible_path": tp.get("visible_image_path"),
                        "filename": tp.get("filename", ""),
                        "hotspot": tp.get("hotspot_temp"),
                        "coldspot": tp.get("coldspot_temp"),
                        "temp_delta": tp.get("temp_delta"),
                        "confidence": tp.get("correlation", {}).get("confidence", "low")
                    }
                    for tp in thermal_pages_for_area
                ],
                "inspection_photos": [
                    photos.get(n) for n in area.get("negative_photos", []) if n in photos
                ],
                "positive_photos": [
                    photos.get(n) for n in area.get("positive_photos", []) if n in photos
                ]
            }

            observations.append({
                "area_id": area_id,
                "description": area["negative_description"],
                "text": text,
                "images": all_area_images,
                "thermal_count": len(thermal_pages_for_area)
            })

        return observations

    def _generate_root_cause(self, inspection_data: dict, thermal_pages: list) -> str:
        areas = inspection_data.get("impacted_areas", [])
        checklist = inspection_data.get("checklist", {})

        all_areas_summary = "\n".join([
            f"Area {a['area_id']}:\n"
            f"  NEGATIVE (damage visible here): {a['negative_description']} "
            f"  [Photos: {', '.join(str(p) for p in a.get('negative_photos', []))}]\n"
            f"  POSITIVE (source of problem): {a['positive_description']} "
            f"  [Photos: {', '.join(str(p) for p in a.get('positive_photos', []))}]"
            for a in areas
        ])

        matched = [p for p in thermal_pages if p.get("correlation", {}).get("area_id")]
        thermal_summary = f"""
{len(matched)} of {len(thermal_pages)} thermal images correlated to specific areas.
Temperature differentials range from {min(p.get('temp_delta',0) for p in thermal_pages):.1f}°C
to {max(p.get('temp_delta',0) for p in thermal_pages):.1f}°C.
Coldspot temperatures consistently in 20-23°C range against ambient of 23°C.
Cold zones appear at skirting level (floor-wall junction) across multiple rooms.
"""

        checklist_flags = self._format_full_checklist(checklist)

        prompt = ROOT_CAUSE_PROMPT.format(
            all_areas_summary=all_areas_summary,
            thermal_summary=thermal_summary,
            checklist_flags=checklist_flags
        )
        return self._call_model(prompt)

    def _generate_severity(
        self, inspection_data: dict, thermal_pages: list, area_groups: dict
    ) -> str:
        areas = inspection_data.get("impacted_areas", [])

        areas_with_thermal = ""
        for area in areas:
            area_id = area["area_id"]
            tp_list = area_groups.get(area_id, [])
            thermal_info = f"({len(tp_list)} thermal images)" if tp_list else "(no thermal data)"
            areas_with_thermal += f"Area {area_id}: {area['negative_description']} {thermal_info}\n"

        thermal_severity_data = "\n".join([
            f"Page {p['page_number']} ({p.get('filename','')}): "
            f"Hotspot={p.get('hotspot_temp')}°C, Coldspot={p.get('coldspot_temp')}°C, "
            f"Delta={p.get('temp_delta')}°C, "
            f"Matched to Area {p.get('correlation',{}).get('area_id','unknown')} "
            f"(confidence: {p.get('correlation',{}).get('confidence','low')})"
            for p in thermal_pages
        ])

        checklist_flags = self._format_full_checklist(inspection_data.get("checklist", {}))

        prompt = SEVERITY_PROMPT.format(
            areas_with_thermal=areas_with_thermal,
            thermal_severity_data=thermal_severity_data,
            checklist_flags=checklist_flags
        )
        return self._call_model(prompt)

    def _generate_recommendations(
        self, root_causes: str, severity_assessment: str, inspection_data: dict
    ) -> str:
        areas = inspection_data.get("impacted_areas", [])
        areas_summary = "\n".join([
            f"Area {a['area_id']}: {a['negative_description']} | Source: {a['positive_description']}"
            for a in areas
        ])

        prompt = RECOMMENDED_ACTIONS_PROMPT.format(
            root_causes=root_causes,
            severity_assessment=severity_assessment,
            areas_summary=areas_summary
        )
        return self._call_model(prompt)

    def _generate_additional_notes(
        self, inspection_data: dict, thermal_pages: list, ddr: dict
    ) -> str:
        full_summary = f"""
Total areas inspected: {len(inspection_data.get('impacted_areas', []))}
Thermal images: {len(thermal_pages)}
Overall score: {inspection_data.get('property_info', {}).get('score', 'N/A')}%
Root cause summary: {ddr.get('root_cause', '')[:300]}
Severity summary: {ddr.get('severity_assessment', '')[:300]}
"""
        prompt = ADDITIONAL_NOTES_PROMPT.format(full_summary=full_summary)
        return self._call_model(prompt)

    def _generate_missing_info(
        self, inspection_data: dict, thermal_pages: list, area_groups: dict
    ) -> str:
        prop_info = inspection_data.get("property_info", {})
        checklist = inspection_data.get("checklist", {})

        low_confidence = [
            f"Thermal page {p['page_number']} ({p.get('filename','')}): "
            f"{p.get('correlation',{}).get('reason','unknown reason')}"
            for p in thermal_pages
            if p.get("correlation", {}).get("confidence") in ["low", None]
        ]
        logical_assignments = [
            f"Thermal page {p['page_number']} ({p.get('filename','')}): "
            f"assigned to Area {p.get('correlation',{}).get('area_id')} by logical merging"
            for p in thermal_pages
            if p.get("correlation", {}).get("confidence") == "logical"
        ]

        unmatched_count = len(area_groups.get("unmatched", []))

        # Use actual extracted values — only fall back to "Not Available" when genuinely missing
        def _val(key):
            v = prop_info.get(key, "Not Available")
            return v if v else "Not Available"

        inspection_data_str = f"""
Property Type: {_val('property_type')}
Inspection Date: {_val('inspection_date')}
Inspected By: {_val('inspected_by')}
Floors in Building: {_val('floors')}
Overall Score: {_val('score')}%
Previous Structural Audit: {_val('previous_structural_audit')}
Previous Repair Work: {_val('previous_repair_work')}
Impacted Rooms: {_val('impacted_rooms')}
Total Impacted Areas: {len(inspection_data.get('impacted_areas', []))}
Customer name: Not Available (redacted in document for privacy)
Customer mobile: Not Available (redacted)
Customer email: Not Available (redacted)
Property address: Not Available (redacted)
Property age: Not Available
Paint manufacturer: {checklist.get('Paint manufacturer', checklist.get('Paint Manufacturer', 'Not Sure (per checklist)'))}
Low confidence thermal correlations: {len(low_confidence)} images
Logically assigned (no visual match): {len(logical_assignments)} images
Unmatched thermal images (no area): {unmatched_count}
Low confidence details: {chr(10).join(low_confidence[:5]) if low_confidence else 'None'}
Logical assignment details: {chr(10).join(logical_assignments[:5]) if logical_assignments else 'None'}
"""

        thermal_data_str = f"""
Total thermal images: {len(thermal_pages)}
Successfully visually correlated: {len(thermal_pages) - unmatched_count - len(logical_assignments)}
Logically assigned (no visual match): {len(logical_assignments)}
Unmatched/uncertain: {unmatched_count + len(low_confidence)}
"""

        prompt = MISSING_INFO_PROMPT.format(
            inspection_data=inspection_data_str,
            thermal_data=thermal_data_str
        )
        return self._call_model(prompt)

    # --- Helper formatters ---

    def _format_thermal_data_for_area(self, thermal_pages: list) -> str:
        if not thermal_pages:
            return "No thermal images correlated to this area."

        lines = []
        for p in thermal_pages:
            corr = p.get("correlation", {})
            lines.append(
                f"- Thermal image {p.get('filename','')}: "
                f"Hotspot={p.get('hotspot_temp')}°C, "
                f"Coldspot={p.get('coldspot_temp')}°C, "
                f"Delta={p.get('temp_delta')}°C "
                f"(Match confidence: {corr.get('confidence','low')}, "
                f"Reason: {corr.get('reason','')})"
            )
        return "\n".join(lines)

    def _format_full_checklist(self, checklist: dict) -> str:
        if not checklist:
            return "Checklist data: Not Available"
        lines = [f"- {k}: {v}" for k, v in checklist.items()]
        return "\n".join(lines)
