# Architecture

## Overview

The pipeline takes an Excel file with survey responses, figures out which columns contain questions, and runs each one through Claude to generate themes.

## Data Flow

```
Excel File + Project Background (optional)
    |
    v
Column Discovery
    - Find ID column (looks for "id", "participant_id", etc.)
    - Find question columns (text responses > 20 chars average)
    |
    v
Question Inference (Claude Opus 4.5)
    - Sample 10 responses from each column
    - Include project background for context
    - Ask Claude: "What question was asked here?"
    - Get natural, specific question text
    |
    v
Parallel Analysis (ThreadPoolExecutor, 6 workers)
    |
    v
For each question column (concurrent):
    |
    v
Response Extraction
    - Parse transcript format ("user: ..." lines)
    - Filter out empty/short responses
    - Build participant ID lookup
    |
    v
Theme Generation (Claude Opus 4.5)
    - Include project background for context
    - Send responses with formatting rules
    - Get back 3-5 themes with participant assignments
    - Parse JSON from response
    |
    v
Quote Selection + Validation
    - Pick up to 3 quotes per theme
    - Model selects best_quote_ids that directly support theme description
    - Track used quotes to prevent duplicates
    - Validate quotes exist in source data
    - Fix mismatched quotes with source text
    |
    v
Summary Generation (GPT-5.1)
    - Send themes with percentages
    - Get headline + 1-2 sentence summary
    - Authoritative executive tone
    |
    v
Post-Processing
    - Calculate theme percentages
    - Sort themes by size
    - Clean up fancy dashes
    - Build classification data for export
    |
    v
Output
    - results.json (main output)
    - report.md (human-readable)
    - classifications/*.xlsx (review files)
```

## Key Design Decisions

**Project background parameter**: The pipeline accepts optional research context that informs question inference and theme generation. This improves theme relevance to research objectives.

**Parallel execution**: Questions are analyzed concurrently using ThreadPoolExecutor (default 6 workers). Each question is independent, so parallelization is straightforward and provides ~6x speedup.

**Classification export**: Every participant → theme assignment is exported to Excel for manual review. This enables accuracy verification and audit trails.

**Quote validation**: Quotes are validated against source data before inclusion. Mismatches are logged and auto-corrected using source text. This prevents hallucination.

**Dual model architecture**: Claude Opus 4.5 handles the heavy lifting (question inference, theme extraction) while GPT-5.1 generates the executive summaries. Opus excels at precise extraction from messy data; GPT-5.1 produces authoritative, executive-grade summaries.

**Temperature tuning**: Different temperatures for different tasks: 0.3 for question inference (natural phrasing), 0.3 for theme extraction (balanced accuracy and variation), 0.5 for summaries (natural variation).

**Variable theme count**: 3-5 themes based on natural clustering in the data. Fewer themes with stronger cohesion beats more themes with overlap.

**Question inference**: Instead of guessing from column names like "vpn_selection", the pipeline samples actual responses and asks Claude Opus 4.5 what question was likely asked. This produces natural, specific questions like "What factors influenced your decision when choosing your VPN?"

**Dynamic question detection**: The pipeline doesn't hardcode question names. It looks at column contents and picks out the ones that look like text responses. This makes it work with any survey structure.

**Quote-description alignment**: The model selects best_quote_ids that directly prove the theme description. If description says "no-logs policies dominate," quotes mention no-logs.

**Quote deduplication**: Quotes are tracked across themes so the same response never appears twice in the output.

**Senior research tone**: Prompts explicitly ask for "$500/hour consultant voice" with no hedging, varied openings, and business implications.

## Components

| File | Purpose |
|------|---------|
| `pipeline.py` | Main analysis logic |
| `report.py` | Converts JSON to Markdown |

## Error Handling

Each question is analyzed independently. If one fails, the others still run and the error gets logged in the output JSON.
