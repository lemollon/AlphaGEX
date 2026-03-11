"""Core Gmail organizer logic - fetches, matches, and organizes emails."""

import logging
import re
from typing import Optional

from .models import Action, EmailMessage, MatchField, Rule, RuleSet

logger = logging.getLogger(__name__)


class GmailOrganizer:
    """Fetches emails from Gmail and applies organization rules."""

    def __init__(self, service, rule_set: RuleSet):
        """
        Args:
            service: An authenticated Gmail API service instance.
            rule_set: The rules to apply to emails.
        """
        self.service = service
        self.rule_set = rule_set

    def fetch_messages(
        self, query: str = "is:inbox", max_results: int = 100
    ) -> list[EmailMessage]:
        """Fetch messages from Gmail matching the given query.

        Args:
            query: Gmail search query string.
            max_results: Maximum number of messages to fetch.

        Returns:
            List of EmailMessage objects.
        """
        messages = []
        results = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )

        raw_messages = results.get("messages", [])
        logger.info("Found %d messages matching query: %s", len(raw_messages), query)

        for raw in raw_messages:
            msg = self._get_message_detail(raw["id"])
            if msg:
                messages.append(msg)

        return messages

    def organize(self, dry_run: bool = False) -> dict:
        """Run all enabled rules against inbox messages.

        Args:
            dry_run: If True, log actions without applying them.

        Returns:
            Summary dict with counts of actions taken per rule.
        """
        messages = self.fetch_messages()
        rules = self.rule_set.get_enabled_rules()
        summary = {}

        for rule in rules:
            matched = [m for m in messages if self._matches(rule, m)]
            summary[rule.name] = {"matched": len(matched), "actions": []}

            if matched:
                logger.info(
                    "Rule '%s' matched %d messages", rule.name, len(matched)
                )

            for msg in matched:
                if dry_run:
                    logger.info(
                        "[DRY RUN] Would apply %s to '%s' from %s",
                        [a.value for a in rule.actions],
                        msg.subject,
                        msg.sender,
                    )
                else:
                    self._apply_actions(rule, msg)
                    summary[rule.name]["actions"].append(msg.id)

        return summary

    def _matches(self, rule: Rule, message: EmailMessage) -> bool:
        """Check if a message matches a rule's criteria."""
        if rule.match_field == MatchField.FROM:
            return bool(re.search(rule.pattern, message.sender, re.IGNORECASE))
        elif rule.match_field == MatchField.TO:
            return bool(re.search(rule.pattern, message.to, re.IGNORECASE))
        elif rule.match_field == MatchField.SUBJECT:
            return bool(re.search(rule.pattern, message.subject, re.IGNORECASE))
        elif rule.match_field == MatchField.BODY:
            return bool(re.search(rule.pattern, message.snippet, re.IGNORECASE))
        elif rule.match_field == MatchField.HAS_ATTACHMENT:
            return message.has_attachment
        return False

    def _apply_actions(self, rule: Rule, message: EmailMessage) -> None:
        """Apply a rule's actions to a message."""
        add_labels = []
        remove_labels = []

        for action in rule.actions:
            if action == Action.LABEL and rule.target_label:
                label_id = self._get_or_create_label(rule.target_label)
                add_labels.append(label_id)
            elif action == Action.ARCHIVE:
                remove_labels.append("INBOX")
            elif action == Action.MARK_READ:
                remove_labels.append("UNREAD")
            elif action == Action.STAR:
                add_labels.append("STARRED")
            elif action == Action.DELETE:
                remove_labels.append("INBOX")
                add_labels.append("TRASH")

        if add_labels or remove_labels:
            body = {}
            if add_labels:
                body["addLabelIds"] = add_labels
            if remove_labels:
                body["removeLabelIds"] = remove_labels

            self.service.users().messages().modify(
                userId="me", id=message.id, body=body
            ).execute()

            logger.info(
                "Applied actions to message '%s': +%s -%s",
                message.subject,
                add_labels,
                remove_labels,
            )

    def _get_message_detail(self, message_id: str) -> Optional[EmailMessage]:
        """Fetch full message details by ID."""
        try:
            msg = (
                self.service.users()
                .messages()
                .get(userId="me", id=message_id, format="metadata")
                .execute()
            )
            headers = {
                h["name"].lower(): h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            parts = msg.get("payload", {}).get("parts", [])
            has_attachment = any(
                p.get("filename") for p in parts if p.get("filename")
            )

            return EmailMessage(
                id=msg["id"],
                thread_id=msg["threadId"],
                subject=headers.get("subject", "(no subject)"),
                sender=headers.get("from", ""),
                to=headers.get("to", ""),
                snippet=msg.get("snippet", ""),
                label_ids=msg.get("labelIds", []),
                has_attachment=has_attachment,
            )
        except Exception as e:
            logger.error("Failed to fetch message %s: %s", message_id, e)
            return None

    def _get_or_create_label(self, label_name: str) -> str:
        """Get a label ID by name, creating it if it doesn't exist."""
        results = self.service.users().labels().list(userId="me").execute()
        labels = results.get("labels", [])

        for label in labels:
            if label["name"].lower() == label_name.lower():
                return label["id"]

        # Create the label
        body = {"name": label_name, "labelListVisibility": "labelShow"}
        created = (
            self.service.users().labels().create(userId="me", body=body).execute()
        )
        logger.info("Created new label: %s (id=%s)", label_name, created["id"])
        return created["id"]
