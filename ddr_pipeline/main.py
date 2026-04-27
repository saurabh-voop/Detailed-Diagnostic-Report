"""
DDR Generation Pipeline - Main Entry Point
Usage: python main.py --inspection <path> --thermal <path> --api-key <key>
       OR set OPENAI_API_KEY in .env file
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    OPENAI_API_KEY, MODEL_NAME,
    INSPECTION_PDF, THERMAL_PDF,
    INSPECTION_PHOTOS_DIR, THERMAL_IMAGES_DIR, OUTPUTS_DIR
)
from ingestion.pdf_extractor import extract_inspection_report, extract_thermal_report
from correlation.matcher import build_correlation_map, group_by_area
from generation.ddr_generator import DDRGenerator
from output.docx_builder import build_ddr_document


def run_pipeline(
    inspection_pdf: str,
    thermal_pdf: str,
    api_key: str,
    output_dir: str,
    skip_correlation: bool = False,
    correlation_cache: str = None
):
    """
    Run the full DDR generation pipeline.
    
    Args:
        inspection_pdf: Path to inspection report PDF
        thermal_pdf: Path to thermal images PDF
        api_key: Gemini API key
        output_dir: Directory for output files
        skip_correlation: If True, load correlation from cache (for development)
        correlation_cache: Path to cached correlation JSON
    """
    start_time = time.time()
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("DDR GENERATION PIPELINE")
    print("=" * 60)

    # ----------------------------------------------------------------
    # STAGE 1: Document Ingestion
    # ----------------------------------------------------------------
    print("\n[Stage 1] Extracting documents...")

    print("  Extracting inspection report...")
    inspection_data = extract_inspection_report(inspection_pdf, INSPECTION_PHOTOS_DIR)
    print(f"  ✓ Inspection: {len(inspection_data['impacted_areas'])} areas, "
          f"{len(inspection_data['photos'])} photos extracted")

    print("  Extracting thermal report...")
    thermal_pages = extract_thermal_report(thermal_pdf, THERMAL_IMAGES_DIR)
    print(f"  ✓ Thermal: {len(thermal_pages)} pages extracted")

    # Save intermediate data
    intermediate_dir = os.path.join(output_dir, "intermediate")
    os.makedirs(intermediate_dir, exist_ok=True)
    
    with open(os.path.join(intermediate_dir, "inspection_data.json"), "w") as f:
        # Photos dict has non-serializable paths, convert to list
        save_data = {k: v for k, v in inspection_data.items() if k != "photos"}
        save_data["photo_count"] = len(inspection_data.get("photos", {}))
        json.dump(save_data, f, indent=2)
    
    thermal_meta = [{k: v for k, v in p.items() 
                     if not k.endswith("_path")} for p in thermal_pages]
    with open(os.path.join(intermediate_dir, "thermal_metadata.json"), "w") as f:
        json.dump(thermal_meta, f, indent=2)

    print(f"  Intermediate data saved to {intermediate_dir}")

    # ----------------------------------------------------------------
    # STAGE 2: Correlation Engine
    # ----------------------------------------------------------------
    cache_path = correlation_cache or os.path.join(intermediate_dir, "correlation_map.json")

    if skip_correlation and os.path.exists(cache_path):
        print(f"\n[Stage 2] Loading correlation from cache: {cache_path}")
        with open(cache_path) as f:
            cached = json.load(f)
        
        # Re-attach correlations to thermal pages
        for i, page in enumerate(thermal_pages):
            if i < len(cached):
                page["correlation"] = cached[i].get("correlation", {})
        
        enriched_thermal_pages = thermal_pages
        print(f"  ✓ Loaded {len(enriched_thermal_pages)} correlations from cache")
    else:
        print(f"\n[Stage 2] Running correlation engine (this takes ~2-3 minutes)...")
        enriched_thermal_pages = build_correlation_map(
            thermal_pages=thermal_pages,
            inspection_data=inspection_data,
            api_key=api_key,
            model_name=MODEL_NAME
        )

        # Cache the results
        cache_data = [{k: v for k, v in p.items() if not k.endswith("_path")} 
                      for p in enriched_thermal_pages]
        with open(cache_path, "w") as f:
            json.dump(cache_data, f, indent=2)
        print(f"  ✓ Correlation complete, cached to {cache_path}")

    # Group by area (logical merging assigns unmatched thermals to empty areas)
    area_groups = group_by_area(enriched_thermal_pages, inspection_data)
    print(f"\n  Correlation summary:")
    for area_id, pages in area_groups.items():
        if area_id != "unmatched":
            print(f"    Area {area_id}: {len(pages)} thermal image(s)")
    unmatched = area_groups.get("unmatched", [])
    if unmatched:
        print(f"    Unmatched: {len(unmatched)} thermal image(s)")

    # ----------------------------------------------------------------
    # STAGE 3: DDR Generation
    # ----------------------------------------------------------------
    print("\n[Stage 3] Generating DDR sections...")
    generator = DDRGenerator(api_key=api_key, model_name=MODEL_NAME)
    
    ddr = generator.generate_full_ddr(
        inspection_data=inspection_data,
        enriched_thermal_pages=enriched_thermal_pages,
        area_groups=area_groups
    )

    # Save generated text
    with open(os.path.join(intermediate_dir, "ddr_sections.json"), "w") as f:
        # Remove image objects from area observations for JSON serialization
        ddr_save = {k: v for k, v in ddr.items() if k != "area_observations"}
        ddr_save["area_observations"] = [
            {k: v for k, v in obs.items() if k != "images"}
            for obs in ddr.get("area_observations", [])
        ]
        json.dump(ddr_save, f, indent=2)

    print("  ✓ All sections generated")

    # ----------------------------------------------------------------
    # STAGE 4: Document Assembly
    # ----------------------------------------------------------------
    print("\n[Stage 4] Assembling DDR document...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"DDR_Report_{timestamp}.docx")
    
    build_ddr_document(
        ddr=ddr,
        inspection_data=inspection_data,
        output_path=output_path
    )

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"PIPELINE COMPLETE in {elapsed:.0f}s")
    print(f"Output: {output_path}")
    print("=" * 60)

    return output_path


def main():
    parser = argparse.ArgumentParser(description="DDR Generation Pipeline")
    parser.add_argument("--inspection", default=INSPECTION_PDF, help="Path to inspection PDF")
    parser.add_argument("--thermal", default=THERMAL_PDF, help="Path to thermal PDF")
    parser.add_argument("--api-key", default=OPENAI_API_KEY, help="OpenAI API key")
    parser.add_argument("--output", default=OUTPUTS_DIR, help="Output directory")
    parser.add_argument(
        "--skip-correlation", action="store_true",
        help="Skip correlation (use cached results for faster dev iteration)"
    )
    parser.add_argument("--correlation-cache", help="Path to correlation cache JSON")

    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: OpenAI API key required. Set OPENAI_API_KEY in .env or pass --api-key")
        sys.exit(1)

    if not os.path.exists(args.inspection):
        print(f"ERROR: Inspection PDF not found: {args.inspection}")
        sys.exit(1)

    if not os.path.exists(args.thermal):
        print(f"ERROR: Thermal PDF not found: {args.thermal}")
        sys.exit(1)

    output_path = run_pipeline(
        inspection_pdf=args.inspection,
        thermal_pdf=args.thermal,
        api_key=args.api_key,
        output_dir=args.output,
        skip_correlation=args.skip_correlation,
        correlation_cache=args.correlation_cache
    )

    print(f"\nDDR report ready: {output_path}")


if __name__ == "__main__":
    main()
