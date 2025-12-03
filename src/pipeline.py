"""
Thematic Analysis Pipeline

Takes survey responses from an Excel file, sends them to Claude,
and gets back organized themes with quotes and summaries.

Questions are extracted dynamically from the Excel columns - no hardcoding.

Models:
- Claude Opus 4.5: Question inference, theme generation (heavy lifting)
- GPT-5.1: Summary generation (authoritative, executive tone)
"""

import os
import json
import sys
import re
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from anthropic import Anthropic
from openai import OpenAI

# Set up API clients
claude = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Model configuration
CLAUDE_MODEL = "claude-opus-4-5-20251101"  # Heavy lifting: inference, themes
OPENAI_MODEL = "gpt-5.1"  # Summaries: authoritative, executive tone

# Concurrency settings
MAX_WORKERS = 6  # Parallel question analysis


def find_question_columns(df):
    """
    Figure out which columns contain survey questions (text responses).
    Skips metadata columns like ID, timestamps, emails, etc.
    """
    skip_patterns = [
        r'^id$', r'_id$', r'timestamp', r'date', r'time', r'email', 
        r'^name$', r'status', r'completed', r'started', r'duration', 
        r'^ip', r'browser', r'device', r'source', r'channel'
    ]
    
    question_cols = []
    
    for col in df.columns:
        col_lower = col.lower()
        
        # Skip if it looks like metadata
        if any(re.search(pattern, col_lower) for pattern in skip_patterns):
            continue
        
        # Skip mostly empty columns
        non_empty = df[col].dropna()
        if len(non_empty) < 5:
            continue
        
        # Check if it contains text (not just numbers or short codes)
        sample = non_empty.head(20).astype(str)
        avg_length = sample.str.len().mean()
        
        # Text responses are usually longer than 20 chars on average
        if avg_length > 20:
            question_cols.append(col)
    
    return question_cols


def column_to_question(column_name):
    """
    Turn a column name into a readable question.
    This is a fallback - prefer infer_question_from_responses when you have data.
    """
    # Replace underscores with spaces
    text = column_name.replace('_', ' ')
    
    # Add spaces before capitals (handles camelCase)
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    
    # Clean up and capitalize
    text = text.strip().lower()
    
    # Make it a question
    return f"What are your thoughts on {text}?"


def infer_question_from_responses(column_name, sample_responses, project_background=""):
    """
    Use Claude to figure out what question was asked based on how people answered.
    Much better than guessing from the column name alone.
    """
    # Take first 10 responses for better inference
    examples = "\n".join([f"- {r[:200]}" for r in sample_responses[:10]])
    
    context_block = ""
    if project_background:
        context_block = f"""Project context:
{project_background}

"""
    
    prompt = f"""{context_block}Look at these survey responses and figure out what question was asked.

Column name: {column_name}

Sample responses:
{examples}

Based on these responses, what specific question was the participant answering?

STRICT RULES:
1. STANDALONE - makes complete sense without any prior context
2. NEVER USE "AND" - absolutely no compound questions. ONE question only.
3. NO BRAND NAMES - say "your VPN" not any specific product name
4. NO REFERENCES - never "you mentioned", "as discussed", "the problems above"
5. CONCISE - under 12 words preferred
6. PICK ONE TOPIC - if responses cover multiple things, pick the MAIN one

FORBIDDEN PATTERNS (never output these):
- "X and Y?" 
- "X and how Y?"
- "Why X and what Y?"
- Any question containing the word "and"

EXAMPLES:
BAD: "What problems have you had and would you want something better?"
GOOD: "What problems have you experienced with your current VPN?"

BAD: "Why did you remove your data and how satisfied were you?"
GOOD: "What motivated you to remove your personal data online?"

BAD: "How appealing is X and what are the benefits?"
GOOD: "How appealing is having a private server location?"

Return ONLY the question. No explanation. Under 12 words. No "and". End with ?"""

    response = ask_claude(prompt, temperature=0.3)  # Natural phrasing
    
    # Clean up the response
    question = response.strip()
    # Remove any quotes that might wrap the question
    question = question.strip('"\'')
    if not question.endswith('?'):
        question += '?'
    
    # If it still has "and", truncate at the "and"
    if ' and ' in question.lower():
        parts = question.split(' and ')
        question = parts[0].strip()
        if not question.endswith('?'):
            question += '?'
    
    return question


def get_user_response(transcript):
    """
    Pull out just what the user said from a transcript.
    Transcripts look like 'user: blah blah' on each line.
    """
    if pd.isna(transcript):
        return ""
    
    lines = str(transcript).split('\n')
    user_parts = []
    
    for line in lines:
        if line.strip().startswith('user:'):
            user_parts.append(line.replace('user:', '').strip())
    
    return ' '.join(user_parts)


def ask_claude(prompt, temperature=0):
    """Send a prompt to Claude Opus 4.5 for extraction tasks."""
    response = claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8192,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


def ask_gpt(prompt):
    """Send a prompt to GPT-5.1 for summaries."""
    response = openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        max_completion_tokens=1024,
        temperature=0.5,  # Natural variation for summaries
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content


def get_json_from_response(text):
    """
    Claude sometimes wraps JSON in code blocks or has minor formatting issues.
    This finds the JSON part and parses it, with some error recovery.
    """
    # Remove markdown code blocks if present
    text = text.replace('```json', '').replace('```', '').strip()
    
    start = text.find('{')
    end = text.rfind('}') + 1
    
    if start == -1 or end == 0:
        return {}
    
    json_str = text[start:end]
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        import re
        
        # Fix 1: Missing ] to close themes array before final }
        json_str = re.sub(r'\]\s*\}\s*\}$', ']\n    }\n  ]\n}', json_str)
        
        # Fix 2: Missing } before closing ] of themes array
        json_str = re.sub(r'"\]\s*\]\s*\}', '"]\n    }\n  ]\n}', json_str)
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {}


def sanitize_background(text):
    """Pass through project background as-is."""
    return text if text else ""


def make_theme_prompt(question, responses, project_background=""):
    """
    Build the prompt that tells Claude how to create themes.
    This is where all the formatting rules live.
    """
    context_block = ""
    if project_background:
        clean_bg = sanitize_background(project_background)
        context_block = f"""PROJECT CONTEXT:
{clean_bg}

Use this context to inform your theme analysis. Themes should be relevant to the research objectives described above.

---

"""
    
    return f"""{context_block}You are a paid senior qualitative researcher at a top consultancy. Executive-grade analysis.

Question: "{question}"

Data:
{responses}

THEME COUNT: Create 3, 4, or 5 themes based on natural clustering in the data.
- 3 themes: When responses cluster tightly into distinct camps
- 4 themes: When a fourth segment is meaningfully distinct
- 5 themes: Only when data genuinely splits five ways

Do NOT default to 5. Fewer themes with stronger cohesion beats more themes with overlap.

Assign EVERY participant to exactly one theme.

Return valid JSON only:
{{
  "themes": [
    {{
      "title": "Under 6 words. Sharp.",
      "description": "3-4 sentences. Senior researcher voice. First sentence = the core insight. Middle = evidence and texture from the data. Final = business implication or strategic read.",
      "participant_ids": ["id1", "id2", ...],
      "best_quote_ids": ["id1", "id2", "id3"]
    }}
  ]
}}

CRITICAL - best_quote_ids: Select 3 participant IDs whose verbatim responses DIRECTLY PROVE your description. Read your description, then pick quotes that a reader would say "yes, that quote proves the point." If your description says "no-logs policies dominate," pick quotes that mention no-logs. If your description says "price wins," pick quotes about cost.

VOICE: You've done 200 of these studies. You see patterns others miss. Confident, direct, zero hedging.

SAY "participants" NOT "users/respondents"

VARY YOUR ATTACK - each theme MUST open differently:

A - Lead with behavior: "They've churned through three VPNs already. Reliability trumps features."

B - Lead with tension: "Security matters but price wins. Premium positioning fails here."

C - Lead with quote hook: "'Just make it work.' Setup friction kills adoption."

D - Lead with contrast: "Unlike the speed crowd, these trade performance for privacy."

E - Lead with data pattern: "No-logs appears in every response. Encryption ranks distant second."

BANNED OPENERS:
- "Participants in this theme..."
- "This group values..."
- "These participants..."
- Any opener starting with "This" or "These"

MAX 1 percentage per theme. Prefer: ratios, rankings, "most/few/nearly all", comparisons."""


def make_summary_prompt(question, themes, project_background=""):
    """Build the prompt for creating the executive summary."""
    theme_lines = [f"- {t['title']}: {t['pct']}%" for t in themes]
    theme_list = "\n".join(theme_lines)
    
    context_block = ""
    if project_background:
        clean_bg = sanitize_background(project_background[:500])
        context_block = f"""Project context: {clean_bg}...

"""
    
    return f"""{context_block}You are a paid senior researcher presenting to C-suite. Authoritative. No hedging.

Question: {question}

Themes:
{theme_list}

Return JSON only:
{{"headline": "Under 8 words. The strategic insight.", "summary": "1-2 sentences ONLY. State the key % breakdown. One actionable recommendation."}}

RULES:
- Say "participants" not "users"
- No em dashes
- No hedging ("seems", "appears", "might", "could")
- Use % symbol
- MAXIMUM 2 sentences"""


def ensure_all_classified(themes, all_participant_ids, response_lookup):
    """
    Ensure every participant is assigned to exactly one theme.
    Removes duplicates across themes and assigns missing participants.
    """
    all_ids = set(all_participant_ids)
    
    # First pass: remove duplicates across themes (keep first occurrence)
    seen = set()
    for theme in themes:
        pids = theme.get("participant_ids", [])
        cleaned = []
        for pid in pids:
            if pid not in seen:
                cleaned.append(pid)
                seen.add(pid)
        theme["participant_ids"] = cleaned
    
    # Find missing participants
    missing = all_ids - seen
    
    if not missing:
        return themes
    
    # Assign missing participants to the largest theme (simple heuristic)
    # In production, would use embedding similarity to find best theme
    if themes and missing:
        largest_theme = max(themes, key=lambda t: len(t.get("participant_ids", [])))
        largest_theme["participant_ids"].extend(list(missing))
    
    return themes


def validate_quotes(themes, response_lookup):
    """
    Validate that all quotes exist in source data.
    Returns themes with validation metadata and fixes any issues.
    """
    validation_issues = []
    
    for theme in themes:
        valid_quotes = []
        for quote in theme.get("quotes", []):
            pid = str(quote.get("participant_id", "")).replace("P", "")
            quote_text = quote.get("quote", "")
            
            # Check if participant exists in source
            if pid not in response_lookup:
                validation_issues.append({
                    "type": "missing_participant",
                    "theme": theme.get("title"),
                    "participant_id": pid
                })
                continue
            
            # Check if quote matches source (allowing for truncation)
            source_text = response_lookup[pid]
            if quote_text not in source_text and source_text not in quote_text:
                # Try fuzzy match - first 50 chars
                if quote_text[:50].lower().strip() != source_text[:50].lower().strip():
                    validation_issues.append({
                        "type": "quote_mismatch",
                        "theme": theme.get("title"),
                        "participant_id": pid,
                        "expected": source_text[:100],
                        "got": quote_text[:100]
                    })
                    # Fix: use source text instead
                    quote["quote"] = source_text
            
            valid_quotes.append(quote)
        
        theme["quotes"] = valid_quotes
    
    return themes, validation_issues


def pick_unique_quotes(themes, all_responses):
    """
    Pick quotes for each theme, making sure we don't repeat any.
    Prioritizes best_quote_ids if available, then falls back to participant_ids.
    Each theme gets up to 3 quotes.
    """
    already_used = set()
    
    for theme in themes:
        quotes_for_theme = []
        
        # Prioritize best_quote_ids, then fall back to participant_ids
        quote_candidates = theme.get("best_quote_ids", []) + theme.get("participant_ids", [])
        
        for participant_id in quote_candidates:
            # Clean up the ID in case it has a P prefix
            clean_id = str(participant_id).replace("P", "")
            
            if clean_id not in all_responses:
                continue
            
            # Check if we've used this quote already
            quote_text = all_responses[clean_id]
            quote_key = quote_text[:100].lower().strip()
            
            if quote_key in already_used:
                continue
            
            if len(quotes_for_theme) >= 3:
                break
            
            already_used.add(quote_key)
            quotes_for_theme.append({
                "participant_id": clean_id,
                "quote": quote_text
            })
        
        theme["quotes"] = quotes_for_theme
    
    return themes


def analyze_one_question(column_name, question_text, data, id_column, project_background=""):
    """
    Run the full analysis for a single question.
    Returns a dict with themes, quotes, headline, and summary.
    """
    print(f"  {column_name}...", end=" ", flush=True)
    
    # Gather all the responses for this question
    responses = []
    for _, row in data.iterrows():
        text = get_user_response(row[column_name])
        if text.strip() and len(text) > 3:
            responses.append({
                "id": str(row[id_column]),
                "text": text
            })
    
    total = len(responses)
    if total == 0:
        print("no responses")
        return {"error": "No valid responses"}
    
    # Format responses for Claude (trim to 180 chars each to save tokens)
    formatted = "\n".join([
        f"[{r['id']}]: \"{r['text'][:180]}\""
        for r in responses
    ])
    
    # Ask Claude to create themes
    theme_prompt = make_theme_prompt(question_text, formatted, project_background)
    theme_response = ask_claude(theme_prompt, temperature=0.3)  # Natural variation in descriptions
    
    try:
        theme_data = get_json_from_response(theme_response)
    except json.JSONDecodeError:
        print("failed to parse themes")
        return {"error": "Failed to parse themes"}
    
    themes = theme_data.get("themes", [])
    if not themes:
        print("no themes generated")
        return {"error": "No themes generated"}
    
    # Build a lookup so we can grab quotes later
    response_lookup = {r["id"]: r["text"] for r in responses}
    all_participant_ids = [r["id"] for r in responses]
    
    # Ensure all participants are classified to exactly one theme
    themes = ensure_all_classified(themes, all_participant_ids, response_lookup)
    
    # Figure out percentages and sort biggest first
    for theme in themes:
        count = len(theme.get("participant_ids", []))
        theme["count"] = count
        theme["pct"] = round(count * 100 / total) if total > 0 else 0
    
    themes = sorted(themes, key=lambda t: t["count"], reverse=True)
    
    # Add quotes (no duplicates across themes)
    themes = pick_unique_quotes(themes, response_lookup)
    
    # Validate quotes against source data
    themes, validation_issues = validate_quotes(themes, response_lookup)
    
    # Ask GPT-5.1 for the summary (authoritative, executive tone)
    summary_prompt = make_summary_prompt(question_text, themes, project_background)
    summary_response = ask_gpt(summary_prompt)
    
    try:
        summary = get_json_from_response(summary_response)
    except json.JSONDecodeError:
        summary = {"headline": "Analysis Complete", "summary": "See themes below."}
    
    print(f"done ({total})")
    
    result = {
        "question": question_text,
        "n_participants": total,
        "headline": summary.get("headline", ""),
        "summary": summary.get("summary", ""),
        "themes": themes,
        "classifications": build_classification_data(themes, response_lookup)
    }
    
    if validation_issues:
        result["validation_issues"] = validation_issues
    
    return result


def build_classification_data(themes, response_lookup):
    """
    Build a flat list of participant -> theme assignments for inspection.
    """
    classifications = []
    for theme in themes:
        theme_title = theme.get("title", "Unknown")
        for pid in theme.get("participant_ids", []):
            clean_id = str(pid).replace("P", "")
            classifications.append({
                "participant_id": clean_id,
                "theme": theme_title,
                "response": response_lookup.get(clean_id, "")[:200]
            })
    return classifications


def export_classifications(results, output_dir):
    """
    Export theme classifications to Excel files for inspection.
    One file per question column.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    for col_name, data in results.items():
        if "error" in data:
            continue
        
        classifications = data.get("classifications", [])
        if not classifications:
            continue
        
        df = pd.DataFrame(classifications)
        
        # Add question context
        df["question"] = data.get("question", col_name)
        
        # Reorder columns
        cols = ["participant_id", "theme", "response", "question"]
        df = df[cols]
        
        # Save to Excel
        filepath = os.path.join(output_dir, f"{col_name}_classifications.xlsx")
        df.to_excel(filepath, index=False)
        print(f"  Exported classifications: {filepath}")
    
    # Also create a combined file
    all_classifications = []
    for col_name, data in results.items():
        if "error" in data:
            continue
        for c in data.get("classifications", []):
            c["column"] = col_name
            c["question"] = data.get("question", col_name)
            all_classifications.append(c)
    
    if all_classifications:
        combined_df = pd.DataFrame(all_classifications)
        combined_path = os.path.join(output_dir, "all_classifications.xlsx")
        combined_df.to_excel(combined_path, index=False)
        print(f"  Exported combined classifications: {combined_path}")


def find_id_column(df):
    """Find the column that contains participant IDs."""
    for col in df.columns:
        if col.lower() in ['id', 'participant_id', 'respondent_id', 'user_id']:
            return col
    # Fall back to first column if no obvious ID column
    return df.columns[0]


def clean_dashes(obj):
    """Replace fancy dashes with regular ones throughout the results."""
    if isinstance(obj, str):
        return obj.replace('—', '-').replace('–', '-')
    elif isinstance(obj, dict):
        return {k: clean_dashes(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_dashes(item) for item in obj]
    return obj


def run(excel_file, output_file, project_background=""):
    """
    Main entry point. Load the data, analyze each question, save results.
    
    Args:
        excel_file: Path to Excel file with survey responses
        output_file: Path to save JSON results
        project_background: Optional context about the research project
                           (used to inform theme analysis and question inference)
    """
    print(f"Loading data from {excel_file}")
    data = pd.read_excel(excel_file)
    print(f"Found {len(data)} rows\n")
    
    if project_background:
        print(f"Using project background ({len(project_background)} chars)\n")
    
    # Find the ID column
    id_column = find_id_column(data)
    print(f"Using '{id_column}' as participant ID column\n")
    
    # Find question columns dynamically
    question_columns = find_question_columns(data)
    print(f"Found {len(question_columns)} question columns:")
    for col in question_columns:
        print(f"  - {col}")
    print()
    
    # Infer the actual questions from responses
    print("Inferring questions from responses...")
    questions = {}
    for col in question_columns:
        # Get sample responses to figure out what was asked
        sample_responses = []
        for _, row in data.iterrows():
            text = get_user_response(row[col])
            if text.strip() and len(text) > 10:
                sample_responses.append(text)
            if len(sample_responses) >= 10:
                break
        
        if sample_responses:
            questions[col] = infer_question_from_responses(col, sample_responses, project_background)
        else:
            questions[col] = column_to_question(col)
        
        print(f"  {col}: {questions[col]}")
    print()
    
    print(f"Analyzing questions (parallel, {MAX_WORKERS} workers):")
    results = {}
    
    # Analyze questions in parallel
    def analyze_wrapper(col):
        return col, analyze_one_question(col, questions[col], data, id_column, project_background)
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(analyze_wrapper, col): col for col in question_columns}
        
        for future in as_completed(futures):
            try:
                col, result = future.result()
                results[col] = result
            except Exception as e:
                col = futures[future]
                print(f"  {col}... failed: {e}")
                results[col] = {"error": str(e)}
    
    # Clean up any fancy dashes
    results = clean_dashes(results)
    
    # Save to file
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to {output_file}")
    
    # Export classification files for inspection
    output_dir = os.path.dirname(output_file) or "output"
    classifications_dir = os.path.join(output_dir, "classifications")
    print("\nExporting classification files for review:")
    export_classifications(results, classifications_dir)
    
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <excel_file> [output_file] [project_background_file]")
        print("Example: python pipeline.py data.xlsx output/results.json background.txt")
        sys.exit(1)
    
    excel_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else "output/results.json"
    
    # Load project background if provided
    project_background = ""
    if len(sys.argv) > 3:
        bg_file = sys.argv[3]
        if os.path.exists(bg_file):
            with open(bg_file, 'r') as f:
                project_background = f.read()
            print(f"Loaded project background from {bg_file}")
    
    run(excel_file, output_file, project_background)
