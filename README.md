# Thematic Analysis Pipeline

LLM-powered thematic analysis for qualitative research using Claude API.

## System Architecture

```mermaid
flowchart TB
    subgraph Input["📥 Input Layer"]
        EXCEL[("Excel File<br/>(.xlsx)")]
        CONFIG["Questions<br/>Config"]
    end

    subgraph Ingestion["🔄 Data Ingestion"]
        LOAD["Load Excel<br/>(pandas)"]
        EXTRACT["Extract User Text<br/>(transcript parsing)"]
        VALIDATE["Validate Responses<br/>(filter empty)"]
    end

    subgraph Analysis["🧠 Analysis Engine"]
        subgraph ThemeGen["Theme Generation"]
            PROMPT1["Build Theme Prompt<br/>(varied metrics rules)"]
            CLAUDE1[("Claude API<br/>Sonnet 4.5")]
            PARSE1["Parse JSON Response"]
        end
        
        subgraph QuoteExt["Quote Extraction"]
            LOOKUP["Build Response Lookup"]
            UNIQUE["Extract Unique Quotes<br/>(no duplicates)"]
            LIMIT["Limit 3 per Theme"]
        end
        
        subgraph SummaryGen["Summary Generation"]
            PROMPT2["Build Summary Prompt"]
            CLAUDE2[("Claude API<br/>Sonnet 4.5")]
            PARSE2["Parse JSON Response"]
        end
    end

    subgraph Processing["⚙️ Post-Processing"]
        CALC["Calculate Percentages"]
        SORT["Sort by Count"]
        CLEAN["Clean Text<br/>(remove em dashes)"]
    end

    subgraph Output["📤 Output Layer"]
        JSON[("results.json")]
        MD[("report.md")]
    end

    EXCEL --> LOAD
    CONFIG --> LOAD
    LOAD --> EXTRACT
    EXTRACT --> VALIDATE
    
    VALIDATE --> PROMPT1
    PROMPT1 --> CLAUDE1
    CLAUDE1 --> PARSE1
    
    PARSE1 --> LOOKUP
    VALIDATE --> LOOKUP
    LOOKUP --> UNIQUE
    UNIQUE --> LIMIT
    
    PARSE1 --> CALC
    CALC --> SORT
    SORT --> PROMPT2
    
    PROMPT2 --> CLAUDE2
    CLAUDE2 --> PARSE2
    
    LIMIT --> CLEAN
    PARSE2 --> CLEAN
    
    CLEAN --> JSON
    JSON --> MD

    style CLAUDE1 fill:#f9f,stroke:#333
    style CLAUDE2 fill:#f9f,stroke:#333
    style JSON fill:#9f9,stroke:#333
    style MD fill:#9f9,stroke:#333
```

## Features

| Feature | Description |
|---------|-------------|
| **3 Themes per Question** | Consistent structure across all analyses |
| **Varied Metrics** | Ratios, rankings, qualitative (max 1% per theme) |
| **Varied Openings** | "Privacy dominates...", "Strong preference exists..." |
| **Unique Quotes** | No duplicates across themes |
| **Deterministic** | Temperature=0 for reproducible results |

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="your-key"
```

## Usage

```bash
# Run analysis
python src/pipeline.py data.xlsx output/results.json

# Generate report
python src/report.py output/results.json output/report.md
```

## Project Structure

```
usercue-thematic-analysis/
├── src/
│   ├── __init__.py
│   ├── pipeline.py        # Main analysis
│   └── report.py          # Report generator
├── tests/
│   ├── __init__.py
│   └── test_pipeline.py   # Unit tests
├── docs/
│   ├── ARCHITECTURE.md
│   └── USAGE.md
├── output/
│   ├── results.json
│   └── report.md
├── .gitignore
├── requirements.txt
└── README.md
```

## Output Format

```json
{
  "question_key": {
    "question": "The question text",
    "n_participants": 105,
    "headline": "Key insight under 12 words",
    "summary": "Two sentences with theme percentages",
    "themes": [
      {
        "title": "Theme title",
        "description": "4-5 sentences with varied metrics",
        "pct": 38,
        "quotes": [
          {"participant_id": "4434", "quote": "What they said"}
        ]
      }
    ]
  }
}
```

## Configuration

| Setting | Value |
|---------|-------|
| Model | claude-sonnet-4-5-20250929 |
| Temperature | 0 |
| Max Tokens | 4096 |

## Example Output

**Privacy and Security Focus** (37%)

Privacy concerns dominate VPN selection criteria, with no-logs policies ranking as the top priority among participants. Identity protection and data encryption emerge as core requirements, while participants frequently mention protection from hackers and tracking. Strong preference exists for anonymous browsing capabilities and IP address masking. This segment represents premium customers willing to invest in verified privacy solutions.

## Tests

```bash
pytest tests/ -v
```

## Docs

- [Architecture](docs/ARCHITECTURE.md)
- [Usage Guide](docs/USAGE.md)
