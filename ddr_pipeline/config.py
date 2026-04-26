import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = "gpt-4o-mini"

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
INPUTS_DIR = os.path.join(DATA_DIR, "inputs")
EXTRACTED_DIR = os.path.join(DATA_DIR, "extracted")
INSPECTION_PHOTOS_DIR = os.path.join(EXTRACTED_DIR, "inspection_photos")
THERMAL_IMAGES_DIR = os.path.join(EXTRACTED_DIR, "thermal_images")
OUTPUTS_DIR = os.path.join(DATA_DIR, "outputs")

INSPECTION_PDF = os.path.join(INPUTS_DIR, "Sample_Report.pdf")
THERMAL_PDF = os.path.join(INPUTS_DIR, "Thermal_Images.pdf")
