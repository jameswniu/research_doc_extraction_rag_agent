# Usage Guide

## Quick Start

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="your-key"

python src/pipeline.py data.xlsx output/results.json
python src/report.py output/results.json output/report.md
```

## Input Requirements

The pipeline works with any Excel file that has:

1. **An ID column** - Named "ID", "participant_id", "respondent_id", or similar. Falls back to the first column if nothing matches.

2. **Question columns** - Any column where responses average more than 20 characters. The pipeline auto-detects these.

### Transcript Format

If your responses are in transcript format, the pipeline extracts just the user parts:

```
user: I really like the privacy features
assistant: Can you tell me more?
user: Especially the no-logs policy
```

Gets extracted as: "I really like the privacy features Especially the no-logs policy"

## Output Files

### JSON (results.json)

```json
{
  "column_name": {
    "question": "What are your thoughts on column name?",
    "n_participants": 105,
    "headline": "Short insight",
    "summary": "Two sentences about the findings.",
    "themes": [
      {
        "title": "Theme Name",
        "description": "Description with varied metrics.",
        "pct": 38,
        "count": 40,
        "participant_ids": ["101", "102"],
        "quotes": [
          {"participant_id": "101", "quote": "What they said"}
        ]
      }
    ]
  }
}
```

### Markdown (report.md)

Human-readable report with headlines, theme descriptions, and quotes.

## Customization

### Changing the model

Edit `ask_claude()` in pipeline.py:

```python
response = claude.messages.create(
    model="claude-sonnet-4-5-20250929",  # Change this
    ...
)
```

### Adjusting column detection

Edit `find_question_columns()` to change:
- Which column names to skip (the `skip_patterns` list)
- Minimum response count (currently 5)
- Minimum average length (currently 20 chars)

### Changing theme count

Edit `make_theme_prompt()` and change "exactly 3 themes" to whatever you need.

## Troubleshooting

**"No valid responses"**
- Check that your Excel has the expected column names
- Make sure responses aren't all empty or very short

**"Failed to parse themes"**
- Usually means Claude returned something unexpected
- Check your API key is valid
- Try running again (rare API hiccups happen)

**Duplicate quotes showing up**
- The deduplication uses first 100 chars of each quote
- Very similar responses might slip through

## Running Tests

```bash
pytest tests/ -v
```
