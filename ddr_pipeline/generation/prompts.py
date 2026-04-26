"""
All prompts for DDR section generation.
Kept separate from logic for easy modification and testing.
"""

SYSTEM_PROMPT = """You are a professional building inspection report writer for UrbanRoof.
Your job is to convert raw inspection data into clear, client-friendly reports.

Rules you MUST follow:
1. Only use facts present in the provided data - do NOT invent information
2. If information is missing, write "Not Available"  
3. If data conflicts, explicitly state the conflict
4. Use simple language that a non-technical property owner can understand
5. Avoid excessive jargon - explain technical terms when used
6. Be specific: mention exact room names, temperatures, photo references
7. Keep severity assessments grounded in the actual data provided"""


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
Negative Side (Impacted Area): {negative_description}
Positive Side (Source Area): {positive_description}

THERMAL DATA FOR THIS AREA:
{thermal_data}

CHECKLIST FINDINGS:
{checklist_data}

Write a clear observation covering:
1. What was visually observed (dampness, cracks, staining etc.)
2. What thermal imaging revealed (temperatures, cold zones)
3. Connection between the visible symptoms and thermal findings
4. Which specific photos document this

Keep language simple and factual. Reference photo numbers where relevant.
Format: Start with "**Area {area_id}: {area_description}**" then write 2-3 paragraphs."""


ROOT_CAUSE_PROMPT = """Based on ALL the inspection findings below, identify the probable root causes of the issues.

ALL IMPACTED AREAS SUMMARY:
{all_areas_summary}

THERMAL FINDINGS SUMMARY:
{thermal_summary}

CHECKLIST FLAGS:
{checklist_flags}

Identify and explain:
1. Primary root cause(s) - what is actually causing the dampness/leakage
2. Secondary contributing factors
3. How issues in different areas are likely connected

Be specific about the cause-and-effect chain. 
Example: "The dampness observed at skirting level in multiple rooms is caused by..."
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
- Note which areas it addresses

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

List any:
1. Information explicitly marked as "Not Available" or "N/A" in the source documents
2. Photo correlations that could not be confidently established
3. Areas mentioned but not fully documented
4. Conflicting data between the inspection report and thermal report
5. Standard inspection items that were not assessed

For each item, clearly state:
- What information is missing
- Why it matters (what decision it affects)
- Whether it can be obtained with a follow-up inspection

Write "Not Available" for each missing item rather than leaving blanks."""
