"""
Report Generator

Takes the JSON analysis output and turns it into a nice Markdown report.
"""

import json
import sys
import os


def create_report(results, output_file):
    """
    Turn analysis results into a readable Markdown report.
    """
    question_order = [
        "vpn_selection",
        "unmet_needs_private_location", 
        "unmet_needs_always_avail",
        "current_vpn_feedback",
        "remove_data_steps_probe_yes",
        "remove_data_steps_probe_no"
    ]
    
    lines = [
        "# Thematic Analysis Results",
        "",
        "VPN/Privacy Market Research",
        ""
    ]
    
    for key in question_order:
        result = results.get(key, {})
        
        # Skip if there was an error or no data
        if "error" in result or not result:
            continue
        
        # Add the question section
        lines.append("---")
        lines.append("")
        lines.append(f"## {result['question']}")
        lines.append("")
        lines.append(f"**Participants:** {result['n_participants']}")
        lines.append("")
        lines.append(f"**Headline:** {result['headline']}")
        lines.append("")
        lines.append(f"**Summary:** {result['summary']}")
        lines.append("")
        lines.append("### Themes")
        lines.append("")
        
        # Add each theme
        for theme in result['themes']:
            lines.append(f"#### {theme['title']} ({theme['pct']}%)")
            lines.append("")
            lines.append(theme['description'])
            lines.append("")
            lines.append("**Quotes:**")
            lines.append("")
            
            # Add quotes
            for quote in theme.get('quotes', []):
                text = quote['quote'].replace('—', '-').replace('–', '-')
                lines.append(f"> \"{text}\"")
                lines.append(">")
                lines.append(f"> - Participant {quote['participant_id']}")
                lines.append("")
        
        lines.append("")
    
    # Write the file
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"Report saved to {output_file}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python report.py <results.json> [output.md]")
        sys.exit(1)
    
    json_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else "output/report.md"
    
    with open(json_file) as f:
        results = json.load(f)
    
    create_report(results, output_file)
