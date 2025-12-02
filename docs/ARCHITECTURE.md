# Architecture

## How It Works

The pipeline reads survey responses, sends them to Claude for analysis, and outputs structured themes with supporting quotes.

## Layers

### Data Layer

Handles getting data in and out.

- Reads Excel files with pandas
- Extracts user text from transcript format
- Filters out empty responses
- Saves JSON and Markdown output

### Analysis Layer

Where Claude does the heavy lifting.

- Builds prompts with formatting rules
- Sends requests to Claude API
- Parses JSON from responses
- Generates themes and summaries

### Processing Layer

Cleans up and organizes results.

- Calculates percentages
- Sorts themes by size
- Picks unique quotes (no duplicates)
- Removes fancy dashes

## Key Decisions

**Why temperature=0?**
Makes results reproducible. Same input gives same output.

**Why truncate to 180 chars?**
Saves tokens without losing meaning. Most responses front-load the important stuff.

**Why max 3 quotes per theme?**
Enough to show the pattern, not so many that it's overwhelming.

**Why check for duplicate quotes?**
Sometimes the same participant shows up in multiple theme candidate lists. We only want their quote once.

## Data Flow

```
Excel -> Extract Text -> Build Prompt -> Claude -> Parse JSON -> Add Quotes -> Clean Text -> Save
```

## Error Handling

Each question is analyzed separately. If one fails, the others still run. Errors get logged in the output JSON so you know what went wrong.
