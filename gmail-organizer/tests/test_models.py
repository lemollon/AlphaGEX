"""Tests for data models."""

import pytest

from gmail_organizer.models import Action, MatchField, Rule, RuleSet, EmailMessage


class TestRule:
    def test_create_rule(self):
        rule = Rule(
            name="Test Rule",
            match_field=MatchField.FROM,
            pattern="test@example.com",
            actions=[Action.ARCHIVE],
        )
        assert rule.name == "Test Rule"
        assert rule.enabled is True

    def test_label_action_requires_target(self):
        with pytest.raises(ValueError, match="target_label is required"):
            Rule(
                name="Bad Rule",
                match_field=MatchField.FROM,
                pattern="test",
                actions=[Action.LABEL],
            )

    def test_label_action_with_target(self):
        rule = Rule(
            name="Good Rule",
            match_field=MatchField.FROM,
            pattern="test",
            actions=[Action.LABEL],
            target_label="MyLabel",
        )
        assert rule.target_label == "MyLabel"


class TestRuleSet:
    def test_empty_rule_set(self):
        rs = RuleSet()
        assert len(rs.rules) == 0

    def test_add_and_filter_rules(self):
        rs = RuleSet()
        rs.add_rule(Rule(
            name="Enabled",
            match_field=MatchField.SUBJECT,
            pattern="test",
            actions=[Action.ARCHIVE],
            enabled=True,
        ))
        rs.add_rule(Rule(
            name="Disabled",
            match_field=MatchField.SUBJECT,
            pattern="test",
            actions=[Action.ARCHIVE],
            enabled=False,
        ))
        assert len(rs.rules) == 2
        assert len(rs.get_enabled_rules()) == 1


class TestEmailMessage:
    def test_create_message(self):
        msg = EmailMessage(
            id="abc123",
            thread_id="thread1",
            subject="Hello",
            sender="alice@example.com",
            to="bob@example.com",
            snippet="This is a test",
            label_ids=["INBOX"],
        )
        assert msg.id == "abc123"
        assert msg.has_attachment is False
