# Architecture

## Overview

The pipeline takes an Excel file with survey responses, figures out which columns contain questions, and runs each one through Claude to generate themes.

## Data Flow

```
Excel File
    |
    v
Column Discovery
    - Find ID column (looks for "id", "participant_id", etc.)
    - Find question columns (text responses > 20 chars average)
    - Generate question text from column names
    |
    v
For each question column:
    |
    v
Response Extraction
    - Parse transcript format ("user: ..." lines)
    - Filter out empty/short responses
    - Build participant ID lookup
    |
    v
Theme Generation (Claude API)
    - Send responses with formatting rules
    - Get back 3 themes with participant assignments
    - Parse JSON from response
    |
    v
Quote Selection
    - Pick up to 3 quotes per theme
    - Track used quotes to prevent duplicates
    |
    v
Summary Generation (Claude API)
    - Send themes with percentages
    - Get headline + 2-sentence summary
    |
    v
Post-Processing
    - Calculate theme percentages
    - Sort themes by size
    - Clean up fancy dashes
    |
    v
Output (JSON + Markdown)
```

## Key Design Decisions

**Dynamic question detection** - The pipeline doesn't hardcode question names. It looks at column contents and picks out the ones that look like text responses. This makes it work with any survey structure.

**Deterministic output** - Temperature=0 means running the same data twice gives the same results.

**Quote deduplication** - Quotes are tracked across themes so the same response never appears twice in the output.

**Varied metrics** - The prompt specifically asks for different metric types (ratios, rankings, qualitative) to avoid repetitive "X% of participants" language.

## Components

| File | Purpose |
|------|---------|
| `pipeline.py` | Main analysis logic |
| `report.py` | Converts JSON to Markdown |

## Error Handling

Each question is analyzed independently. If one fails, the others still run and the error gets logged in the output JSON.
