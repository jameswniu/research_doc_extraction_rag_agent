"""
Tests for the pipeline functions.

Run with: pytest tests/ -v
"""

import pytest
import json
import sys
sys.path.insert(0, '../src')

from src.pipeline import (
    get_user_response,
    get_json_from_response,
    pick_unique_quotes,
    clean_dashes,
    make_theme_prompt,
    make_summary_prompt,
    QUESTIONS
)


class TestGetUserResponse:
    """Make sure we can pull user text from transcripts correctly."""
    
    def test_grabs_user_lines(self):
        transcript = "user: Hello\nassistant: Hi there\nuser: Thanks"
        result = get_user_response(transcript)
        assert result == "Hello Thanks"
    
    def test_handles_empty_input(self):
        assert get_user_response("") == ""
        assert get_user_response(None) == ""
    
    def test_ignores_assistant_lines(self):
        transcript = "assistant: How can I help?\nassistant: Anything else?"
        result = get_user_response(transcript)
        assert result == ""


class TestGetJsonFromResponse:
    """Make sure we can find JSON even when Claude wraps it in text."""
    
    def test_finds_json_in_text(self):
        text = 'Here is your JSON: {"name": "test"} Hope that helps!'
        result = get_json_from_response(text)
        assert result == {"name": "test"}
    
    def test_returns_empty_when_no_json(self):
        result = get_json_from_response("no json here at all")
        assert result == {}
    
    def test_handles_nested_json(self):
        text = '{"themes": [{"title": "Test", "ids": [1, 2]}]}'
        result = get_json_from_response(text)
        assert result["themes"][0]["title"] == "Test"


class TestPickUniqueQuotes:
    """Make sure quotes don't repeat across themes."""
    
    def test_grabs_quotes_for_each_theme(self):
        themes = [
            {"participant_ids": ["1", "2", "3"]},
            {"participant_ids": ["4", "5"]}
        ]
        responses = {
            "1": "First quote",
            "2": "Second quote",
            "3": "Third quote",
            "4": "Fourth quote",
            "5": "Fifth quote"
        }
        
        result = pick_unique_quotes(themes, responses)
        
        assert len(result[0]["quotes"]) == 3
        assert len(result[1]["quotes"]) == 2
    
    def test_no_duplicate_quotes(self):
        themes = [
            {"participant_ids": ["1", "2"]},
            {"participant_ids": ["1", "3"]}  # participant 1 appears twice
        ]
        responses = {
            "1": "Same quote for both",
            "2": "Different quote",
            "3": "Another one"
        }
        
        result = pick_unique_quotes(themes, responses)
        
        # Count how many times the duplicate appears
        all_quotes = []
        for theme in result:
            for q in theme["quotes"]:
                all_quotes.append(q["quote"])
        
        assert all_quotes.count("Same quote for both") == 1
    
    def test_max_three_per_theme(self):
        themes = [{"participant_ids": ["1", "2", "3", "4", "5"]}]
        responses = {str(i): f"Quote number {i}" for i in range(1, 6)}
        
        result = pick_unique_quotes(themes, responses)
        
        assert len(result[0]["quotes"]) == 3


class TestCleanDashes:
    """Make sure we swap out fancy dashes for regular ones."""
    
    def test_fixes_em_dashes(self):
        assert clean_dashes("hello—world") == "hello-world"
        assert clean_dashes("hello–world") == "hello-world"
    
    def test_works_on_nested_stuff(self):
        data = {
            "text": "hello—world",
            "list": ["item—one", "item–two"],
            "nested": {"key": "value—here"}
        }
        
        result = clean_dashes(data)
        
        assert result["text"] == "hello-world"
        assert result["list"][0] == "item-one"
        assert result["nested"]["key"] == "value-here"


class TestPromptBuilders:
    """Check that prompts include the right stuff."""
    
    def test_theme_prompt_has_question(self):
        prompt = make_theme_prompt("What do you think?", "some response data")
        assert "What do you think?" in prompt
        assert "some response data" in prompt
    
    def test_theme_prompt_has_rules(self):
        prompt = make_theme_prompt("Q", "data")
        assert "participants" in prompt.lower()
        assert "3 themes" in prompt.lower()
    
    def test_summary_prompt_lists_themes(self):
        themes = [
            {"title": "Theme A", "pct": 40},
            {"title": "Theme B", "pct": 35},
            {"title": "Theme C", "pct": 25}
        ]
        
        prompt = make_summary_prompt("Some question?", themes)
        
        assert "Theme A: 40%" in prompt
        assert "Theme B: 35%" in prompt
        assert "Theme C: 25%" in prompt


class TestQuestionConfig:
    """Make sure all our questions are set up right."""
    
    def test_all_questions_exist(self):
        expected = [
            "vpn_selection",
            "unmet_needs_private_location",
            "unmet_needs_always_avail",
            "current_vpn_feedback",
            "remove_data_steps_probe_yes",
            "remove_data_steps_probe_no"
        ]
        
        for q in expected:
            assert q in QUESTIONS
    
    def test_questions_arent_empty(self):
        for key, text in QUESTIONS.items():
            assert len(text) > 10, f"{key} question is too short"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
