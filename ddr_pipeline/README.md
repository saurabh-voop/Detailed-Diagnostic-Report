# DDR Generation Pipeline

An AI system that reads building inspection documents and generates a structured Detailed Diagnostic Report (DDR).

## Architecture

```
[Inspection PDF] ──┐
                   ├──► [Stage 1: Ingestion] ──► [Stage 2: Correlation] ──► [Stage 3: Generation] ──► [Stage 4: Assembly] ──► DDR.docx
[Thermal PDF]   ──┘
```

### Stage 1 — Document Ingestion (`ingestion/pdf_extractor.py`)
- Extracts text, structured data, and images from both PDFs using PyMuPDF
- Parses inspection areas, checklists, summary table
- Renders thermal pages as image pairs (thermal capture + visible light photo)

### Stage 2 — Correlation Engine (`correlation/matcher.py`)
- Uses Gemini 1.5 Flash vision to visually match thermal visible-light photos to inspection report photos
- Builds a mapping: `thermal_page → inspection_photo_number → impacted_area`
- Assigns confidence levels (high/medium/low) per match
- Caches results to JSON for re-use during development

### Stage 3 — DDR Generation (`generation/ddr_generator.py`)
- Generates each DDR section separately using Gemini 1.5 Flash
- Section-by-section approach for accuracy and debuggability
- All prompts in `generation/prompts.py` — easily modified

### Stage 4 — Document Assembly (`output/docx_builder.py`)
- Assembles final Word document using python-docx
- Embeds thermal + visible images in correct area sections
- Color-coded severity assessment
- Professional formatting with cover page and table of contents

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your Gemini API key
```

Get a free API key at: https://aistudio.google.com

## Usage

```bash
# Full pipeline (default input PDFs)
python main.py

# Custom inputs
python main.py --inspection path/to/report.pdf --thermal path/to/thermal.pdf

# Skip correlation (use cache for faster dev iteration)
python main.py --skip-correlation

# With explicit API key
python main.py --api-key YOUR_KEY
```

## Output

- `data/outputs/DDR_Report_YYYYMMDD_HHMMSS.docx` — Final DDR document
- `data/outputs/intermediate/inspection_data.json` — Parsed inspection data
- `data/outputs/intermediate/thermal_metadata.json` — Thermal page metadata
- `data/outputs/intermediate/correlation_map.json` — Visual correlation results
- `data/outputs/intermediate/ddr_sections.json` — Generated text sections

## DDR Structure

1. Property Issue Summary
2. Area-wise Observations (with thermal + site photos)
3. Probable Root Cause
4. Severity Assessment (color-coded)
5. Recommended Actions
6. Additional Notes
7. Missing or Unclear Information

## Tech Stack

| Component | Tool |
|-----------|------|
| Language | Python 3.11 |
| PDF Processing | PyMuPDF (fitz) |
| Vision + LLM | Gemini 1.5 Flash (free tier) |
| Document Output | python-docx |
| Config | python-dotenv |

## Limitations & Design Decisions

- **Correlation confidence**: Visual matching of low-quality photos is probabilistic. Low-confidence matches are flagged in the report.
- **No LangChain**: The pipeline is sequential — added framework overhead would reduce debuggability without adding capability.
- **Caching**: Correlation results are cached to JSON, so Stage 2 doesn't re-run on every iteration during development.
- **Rate limiting**: Gemini Flash free tier allows 15 RPM. 4-second delays between calls keep us within limits.
- **Generalizable**: The system is designed for any similar inspection report format, not hardcoded to these specific documents.
