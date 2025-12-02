"""
Thematic Analysis Pipeline

Takes survey responses from an Excel file, sends them to Claude,
and gets back organized themes with quotes and summaries.

Questions are extracted dynamically from the Excel columns - no hardcoding.

Models:
- Claude Opus 4.5: Question inference, theme generation (heavy lifting)
- GPT-5.1: Summary generation (warmer, more conversational)
"""

import os
import json
import sys
import re
import pandas as pd
from anthropic import Anthropic
from openai import OpenAI

# Set up API clients
claude = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Model configuration
CLAUDE_MODEL = "claude-opus-4-5-20251101"  # Heavy lifting: inference, themes
OPENAI_MODEL = "gpt-5.1"  # Summaries: warmer, conversational


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


def infer_question_from_responses(column_name, sample_responses):
    """
    Use Claude to figure out what question was asked based on how people answered.
    Much better than guessing from the column name alone.
    """
    # Take first 10 responses for better inference
    examples = "\n".join([f"- {r[:200]}" for r in sample_responses[:10]])
    
    prompt = f"""Look at these survey responses and figure out what question was asked.

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

    response = ask_claude(prompt)
    
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


def ask_claude(prompt):
    """Send a prompt to Claude Opus 4.5 for heavy lifting tasks."""
    response = claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8192,
        temperature=0,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


def ask_gpt(prompt):
    """Send a prompt to GPT-5.1 for warmer, conversational summaries."""
    response = openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        max_completion_tokens=1024,
        temperature=0,
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
        # Pattern: ]\n  }\n} should be ]\n    }\n  ]\n}
        json_str = re.sub(r'\]\s*\}\s*\}$', ']\n    }\n  ]\n}', json_str)
        
        # Fix 2: Missing } before closing ] of themes array
        json_str = re.sub(r'"\]\s*\]\s*\}', '"]\n    }\n  ]\n}', json_str)
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {}


def make_theme_prompt(question, responses):
    """
    Build the prompt that tells Claude how to create themes.
    This is where all the formatting rules live.
    """
    return f"""You are a senior researcher. Executive clarity.

Question: "{question}"

Data:
{responses}

Create exactly 3 themes. Assign EVERY participant to one theme.

Return valid JSON only:
{{
  "themes": [
    {{
      "title": "Theme title under 8 words",
      "description": "4-5 sentences with 2-3 DIFFERENT metrics. Mention specific features from data. End with business implication.",
      "participant_ids": ["id1", "id2", ...]
    }}
  ]
}}

TERMINOLOGY: Say "participants" NOT "users/respondents/consumers"

VARIED SENTENCE OPENINGS - do NOT always start with "Participants":
- "Privacy concerns dominate...", "Security drives...", "Strong interest exists..."
- "Technical complexity prevents...", "Cost sensitivity limits..."
- "No-logs policies emerge as...", "Speed and reliability rank..."

CRITICAL: VARY YOUR METRICS - do NOT overuse percentages. Use MAX 1 percentage per theme.

Instead of percentages, prefer these metric types:
- Ratio: "Privacy outweighs cost 3:1", "Speed concerns outnumber security issues 2:1"
- Ranking: "No-logs policies rank as the top priority", "Speed emerges as the primary concern"
- Qualitative: "Strong preference exists for...", "Significant resistance appears toward..."
- Comparative: "Speed matters more than price", "Convenience outweighs security for this segment"
- Proportion words: "most", "majority", "half", "minority", "few", "nearly all"

BAD example (too many %):
"65% prioritize privacy. Within this group, 70% mention encryption and 55% focus on no-logs. Roughly 80% express concern."

GOOD example (varied metrics):
"Privacy concerns dominate selection criteria, with no-logs policies ranking as the top priority. Encryption strength matters more than server count for this segment. Strong preference exists for transparent security certifications, and most participants specifically mention identity protection. This represents premium customers willing to pay for verified privacy."

Each theme should use DIFFERENT metric types from other themes."""


def make_summary_prompt(question, themes):
    """Build the prompt for creating the executive summary."""
    theme_lines = [f"- {t['title']}: {t['pct']}%" for t in themes]
    theme_list = "\n".join(theme_lines)
    
    return f"""Executive summary.

Question: {question}

Themes:
{theme_list}

Return JSON only:
{{"headline": "Under 12 words. Key insight. Say 'participants' NOT 'users'.", "summary": "2 sentences. All three theme %. One recommendation. Say 'participants' NOT 'users'. NO counts."}}

No em dashes."""


def pick_unique_quotes(themes, all_responses):
    """
    Pick quotes for each theme, making sure we don't repeat any.
    Each theme gets up to 3 quotes.
    """
    already_used = set()
    
    for theme in themes:
        quotes_for_theme = []
        
        for participant_id in theme.get("participant_ids", []):
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


def analyze_one_question(column_name, question_text, data, id_column):
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
    theme_prompt = make_theme_prompt(question_text, formatted)
    theme_response = ask_claude(theme_prompt)
    
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
    
    # Figure out percentages and sort biggest first
    for theme in themes:
        count = len(theme.get("participant_ids", []))
        theme["count"] = count
        theme["pct"] = round(count * 100 / total) if total > 0 else 0
    
    themes = sorted(themes, key=lambda t: t["count"], reverse=True)
    
    # Add quotes (no duplicates across themes)
    themes = pick_unique_quotes(themes, response_lookup)
    
    # Ask GPT-5.1 for the summary (warmer, more conversational)
    summary_prompt = make_summary_prompt(question_text, themes)
    summary_response = ask_gpt(summary_prompt)
    
    try:
        summary = get_json_from_response(summary_response)
    except json.JSONDecodeError:
        summary = {"headline": "Analysis Complete", "summary": "See themes below."}
    
    print(f"done ({total})")
    
    return {
        "question": question_text,
        "n_participants": total,
        "headline": summary.get("headline", ""),
        "summary": summary.get("summary", ""),
        "themes": themes
    }


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


def run(excel_file, output_file):
    """
    Main entry point. Load the data, analyze each question, save results.
    """
    print(f"Loading data from {excel_file}")
    data = pd.read_excel(excel_file)
    print(f"Found {len(data)} rows\n")
    
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
            questions[col] = infer_question_from_responses(col, sample_responses)
        else:
            questions[col] = column_to_question(col)
        
        print(f"  {col}: {questions[col]}")
    print()
    
    print("Analyzing questions:")
    results = {}
    
    for col in question_columns:
        question_text = questions[col]
        try:
            results[col] = analyze_one_question(col, question_text, data, id_column)
        except Exception as e:
            print(f"failed: {e}")
            results[col] = {"error": str(e)}
    
    # Clean up any fancy dashes
    results = clean_dashes(results)
    
    # Save to file
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to {output_file}")
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <excel_file> [output_file]")
        print("Example: python pipeline.py data.xlsx output/results.json")
        sys.exit(1)
    
    excel_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else "output/results.json"
    
    run(excel_file, output_file)
