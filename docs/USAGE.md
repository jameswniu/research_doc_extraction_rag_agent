# Usage Guide

## Quick Start

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="your-key"
python src/pipeline.py data.xlsx output/results.json
python src/report.py output/results.json output/report.md
```

## Input Format

Your Excel file needs these columns:

| Column | What it is |
|--------|------------|
| `ID` | Participant ID |
| `vpn_selection` | Their response about VPN selection |
| `unmet_needs_private_location` | Their response about private servers |
| ... | Other question columns |

Each cell should have transcript text like:

```
user: This is what they said
assistant: Follow-up question
user: More of their response
```

The pipeline only looks at lines starting with `user:`.

## Output

### JSON (results.json)

```json
{
  "vpn_selection": {
    "question": "When choosing a VPN...",
    "n_participants": 105,
    "headline": "Short insight",
    "summary": "Two sentences with percentages",
    "themes": [
      {
        "title": "Theme Name",
        "description": "What this theme is about",
        "pct": 38,
        "quotes": [...]
      }
    ]
  }
}
```

### Markdown (report.md)

A readable report with headlines, summaries, themes, and quotes.

## Adding New Questions

Edit `QUESTIONS` in pipeline.py:

```python
QUESTIONS = {
    "your_new_key": "Your new question text?",
    ...
}
```

Then make sure your Excel has a column with that key.

## Troubleshooting

**"No valid responses"**
Check that your Excel column names match the keys in QUESTIONS.

**"Failed to parse themes"**
Usually means Claude's response wasn't valid JSON. Check your API key and try again.

**Quotes repeating**
Shouldn't happen, but if it does, check `pick_unique_quotes` in pipeline.py.

## Running Tests

```bash
pytest tests/ -v
```
