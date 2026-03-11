"""Tests for YAML rules loading."""

from pathlib import Path
from textwrap import dedent

from gmail_organizer.models import Action, MatchField
from gmail_organizer.rules_loader import load_rules


def test_load_missing_file(tmp_path):
    result = load_rules(tmp_path / "nonexistent.yaml")
    assert len(result.rules) == 0


def test_load_valid_rules(tmp_path):
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(dedent("""\
        rules:
          - name: "Test Rule"
            match_field: "from"
            pattern: "test@example"
            actions: ["archive", "mark_read"]
          - name: "Label Rule"
            match_field: "subject"
            pattern: "invoice"
            actions: ["label"]
            target_label: "Invoices"
    """))

    result = load_rules(rules_file)
    assert len(result.rules) == 2
    assert result.rules[0].name == "Test Rule"
    assert result.rules[0].match_field == MatchField.FROM
    assert Action.ARCHIVE in result.rules[0].actions
    assert result.rules[1].target_label == "Invoices"


def test_skip_invalid_rules(tmp_path):
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(dedent("""\
        rules:
          - name: "Valid"
            match_field: "from"
            pattern: "test"
            actions: ["archive"]
          - name: "Invalid - bad field"
            match_field: "nonexistent"
            pattern: "test"
            actions: ["archive"]
    """))

    result = load_rules(rules_file)
    assert len(result.rules) == 1
    assert result.rules[0].name == "Valid"
