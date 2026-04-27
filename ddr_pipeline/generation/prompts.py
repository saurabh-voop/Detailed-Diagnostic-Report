"""
All prompts for DDR section generation.
Kept separate from logic for easy modification and testing.
"""

SYSTEM_PROMPT = """You are a professional building inspection report writer for UrbanRoof.
Your job is to convert raw inspection data into clear, client-friendly reports.

Rules you MUST follow:
1. Only use facts present in the provided data - do NOT invent information
2. Only write "Not Available" if the information is genuinely absent from the source data
3. If data conflicts, explicitly state the conflict
4. Use simple language that a non-technical property owner can understand
5. Avoid excessive jargon - explain technical terms when used
6. Be specific: mention exact room names, temperatures, photo references
7. Keep severity assessments grounded in the actual data provided
8. Always scan ALL provided data fields before writing — never mark something
   "Not Available" if it appears anywhere in the data given to you"""


PROPERTY_SUMMARY_PROMPT = """Based on the inspection data below, write a Property Issue Summary section for a DDR report.

INSPECTION DATA:
{inspection_summary}

THERMAL DATA OVERVIEW:
{thermal_overview}

Write a concise executive summary (3-5 sentences) covering:
- What property was inspected and when
- Overall condition and score
- Main categories of issues found
- Urgency level

Use plain English. No bullet points. Write as flowing paragraphs."""


AREA_OBSERVATION_PROMPT = """Write the Area-wise Observation section for Area {area_id}: {area_description}

INSPECTION FINDINGS:
Negative Side (Impacted/Damaged Area): {negative_description}
  Photos documenting damage: {negative_photos}

Positive Side (Source of Problem): {positive_description}
  Photos documenting source: {positive_photos}

POSITIVE→NEGATIVE CAUSAL LINK:
The issue on the Positive Side (source: {positive_description}) is CAUSING the damage
visible on the Negative Side ({negative_description}). You MUST explicitly describe
this cause-and-effect relationship in your observation — e.g., "The defects at the
source location above/adjacent are allowing moisture to migrate and appear as..."

THERMAL DATA FOR THIS AREA:
{thermal_data}

CHECKLIST FINDINGS:
{checklist_data}

Write a clear observation covering:
1. What was visually observed at the NEGATIVE side (dampness, cracks, staining, etc.)
2. What was found at the POSITIVE side (source of water/moisture entry)
3. The causal connection — how the positive-side defect creates the negative-side symptom
4. What thermal imaging revealed (temperatures, cold zones confirming moisture presence)
5. Which specific photo numbers document each finding

Keep language simple and factual. Always reference the actual photo numbers listed above.
Format: Start with "**Area {area_id}: {area_description}**" then write 2-3 paragraphs."""


ROOT_CAUSE_PROMPT = """Based on ALL the inspection findings below, identify the probable root causes of the issues.

ALL IMPACTED AREAS — POSITIVE (SOURCE) → NEGATIVE (DAMAGE) MAPPING:
{all_areas_summary}

THERMAL FINDINGS SUMMARY:
{thermal_summary}

CHECKLIST FLAGS:
{checklist_flags}

Identify and explain:
1. Primary root cause(s) — what is actually causing moisture entry at the source (positive) sides
2. How moisture travels from the positive (source) side to create visible damage on the negative side
3. Cross-area connections — e.g., "The gaps in the Master Bedroom Bathroom (positive side)
   allow water to seep through the slab, appearing as dampness in the Kitchen below (negative side)"
4. Secondary contributing factors (material failure, lack of waterproofing, etc.)

Be explicit about the positive-to-negative moisture pathway in each case.
Write as clear paragraphs, not just a list."""


SEVERITY_PROMPT = """Assess the severity of each issue found in this inspection.

AREAS AND FINDINGS:
{areas_with_thermal}

THERMAL TEMPERATURE DATA:
{thermal_severity_data}

CHECKLIST FLAGS:
{checklist_flags}

For each area, provide:
- Severity level: Critical / High / Medium / Low
- Reasoning based on the actual data
- Whether it requires immediate attention

Also provide an overall property severity rating.

Format each area as:
Area [N] - [Description]: [SEVERITY LEVEL]
Reason: [specific data-based reasoning]"""


RECOMMENDED_ACTIONS_PROMPT = """Based on the root causes and severity assessment, provide recommended repair actions.

ROOT CAUSES IDENTIFIED:
{root_causes}

SEVERITY ASSESSMENT:
{severity_assessment}

AREAS AFFECTED:
{areas_summary}

Provide recommendations in order of priority:
1. Immediate actions (to prevent further damage)
2. Short-term repairs (within 1-3 months)
3. Long-term solutions (waterproofing, structural)

For each recommendation:
- State what needs to be done in plain language
- Explain why it will solve the problem
- Note which areas (positive and negative sides) it addresses

Do not recommend specific product brands or give cost estimates."""


ADDITIONAL_NOTES_PROMPT = """Review all the inspection data and add any additional notes that are important for the client.

FULL INSPECTION SUMMARY:
{full_summary}

Include:
1. Any patterns observed across multiple areas that suggest a systemic issue
2. Areas that appear fine currently but should be monitored
3. Any safety concerns
4. Recommended follow-up inspection timeline

Write as brief, clear paragraphs. Only include what is genuinely useful to the client."""


MISSING_INFO_PROMPT = """Review the inspection data and identify what information is missing or unclear.

INSPECTION DATA:
{inspection_data}

THERMAL DATA:
{thermal_data}

IMPORTANT: Before listing anything as "Not Available", check whether it appears anywhere
in the data provided to you above. Only flag items that are genuinely absent.

List any:
1. Information explicitly marked as "Not Available" or "N/A" in the source documents
2. Photo correlations that could not be confidently established (confidence = "low")
3. Thermal images assigned by logical merging rather than visual match (confidence = "logical")
4. Areas mentioned but not fully documented
5. Conflicting data between the inspection report and thermal report
6. Standard inspection items that were not assessed

For each item, clearly state:
- What information is missing
- Why it matters (what decision it affects)
- Whether it can be obtained with a follow-up inspection

Write "Not Available" only for each item that is genuinely missing — do not flag data
that is present in the provided fields above."""
