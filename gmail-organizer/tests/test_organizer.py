"""Tests for the organizer matching logic."""

from unittest.mock import MagicMock

from gmail_organizer.models import Action, EmailMessage, MatchField, Rule, RuleSet
from gmail_organizer.organizer import GmailOrganizer


def _make_message(**kwargs) -> EmailMessage:
    defaults = dict(
        id="msg1",
        thread_id="t1",
        subject="Test Subject",
        sender="sender@example.com",
        to="me@example.com",
        snippet="Hello world",
        label_ids=["INBOX"],
        has_attachment=False,
    )
    defaults.update(kwargs)
    return EmailMessage(**defaults)


class TestMatching:
    def setup_method(self):
        self.service = MagicMock()
        self.rule_set = RuleSet()
        self.organizer = GmailOrganizer(self.service, self.rule_set)

    def test_match_from_field(self):
        rule = Rule(
            name="From match",
            match_field=MatchField.FROM,
            pattern="sender@example",
            actions=[Action.ARCHIVE],
        )
        msg = _make_message(sender="sender@example.com")
        assert self.organizer._matches(rule, msg) is True

    def test_no_match_from_field(self):
        rule = Rule(
            name="No match",
            match_field=MatchField.FROM,
            pattern="other@example",
            actions=[Action.ARCHIVE],
        )
        msg = _make_message(sender="sender@example.com")
        assert self.organizer._matches(rule, msg) is False

    def test_match_subject_regex(self):
        rule = Rule(
            name="Subject regex",
            match_field=MatchField.SUBJECT,
            pattern="receipt|invoice",
            actions=[Action.ARCHIVE],
        )
        msg = _make_message(subject="Your invoice #1234")
        assert self.organizer._matches(rule, msg) is True

    def test_match_case_insensitive(self):
        rule = Rule(
            name="Case test",
            match_field=MatchField.SUBJECT,
            pattern="URGENT",
            actions=[Action.STAR],
        )
        msg = _make_message(subject="This is urgent please read")
        assert self.organizer._matches(rule, msg) is True

    def test_match_has_attachment(self):
        rule = Rule(
            name="Attachment",
            match_field=MatchField.HAS_ATTACHMENT,
            pattern="true",
            actions=[Action.STAR],
        )
        msg = _make_message(has_attachment=True)
        assert self.organizer._matches(rule, msg) is True

    def test_no_match_has_attachment(self):
        rule = Rule(
            name="No attachment",
            match_field=MatchField.HAS_ATTACHMENT,
            pattern="true",
            actions=[Action.STAR],
        )
        msg = _make_message(has_attachment=False)
        assert self.organizer._matches(rule, msg) is False
