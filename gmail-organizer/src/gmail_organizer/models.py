"""Data models for Gmail Organizer rules and messages."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Action(str, Enum):
    """Actions that can be applied to matching emails."""
    LABEL = "label"
    ARCHIVE = "archive"
    MARK_READ = "mark_read"
    STAR = "star"
    DELETE = "delete"
    MOVE = "move"


class MatchField(str, Enum):
    """Email fields to match rules against."""
    FROM = "from"
    TO = "to"
    SUBJECT = "subject"
    BODY = "body"
    HAS_ATTACHMENT = "has_attachment"


@dataclass
class Rule:
    """A single organizing rule that matches emails and applies actions."""
    name: str
    match_field: MatchField
    pattern: str
    actions: list[Action]
    target_label: Optional[str] = None
    enabled: bool = True

    def __post_init__(self):
        if Action.LABEL in self.actions and not self.target_label:
            raise ValueError("target_label is required when using the LABEL action")


@dataclass
class RuleSet:
    """A collection of organizing rules."""
    rules: list[Rule] = field(default_factory=list)

    def add_rule(self, rule: Rule) -> None:
        self.rules.append(rule)

    def get_enabled_rules(self) -> list[Rule]:
        return [r for r in self.rules if r.enabled]


@dataclass
class EmailMessage:
    """Simplified representation of a Gmail message."""
    id: str
    thread_id: str
    subject: str
    sender: str
    to: str
    snippet: str
    label_ids: list[str]
    has_attachment: bool = False
