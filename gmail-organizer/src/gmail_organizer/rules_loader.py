"""Load organizing rules from YAML configuration files."""

import logging
from pathlib import Path

import yaml

from .models import Action, MatchField, Rule, RuleSet

logger = logging.getLogger(__name__)

DEFAULT_RULES_PATH = Path("config/rules.yaml")


def load_rules(path: Path = DEFAULT_RULES_PATH) -> RuleSet:
    """Load rules from a YAML file.

    Args:
        path: Path to the YAML rules file.

    Returns:
        A RuleSet populated with the rules from the file.
    """
    if not path.exists():
        logger.warning("Rules file not found at %s, using empty rule set", path)
        return RuleSet()

    with open(path) as f:
        data = yaml.safe_load(f)

    rule_set = RuleSet()

    for entry in data.get("rules", []):
        try:
            rule = Rule(
                name=entry["name"],
                match_field=MatchField(entry["match_field"]),
                pattern=entry["pattern"],
                actions=[Action(a) for a in entry["actions"]],
                target_label=entry.get("target_label"),
                enabled=entry.get("enabled", True),
            )
            rule_set.add_rule(rule)
            logger.debug("Loaded rule: %s", rule.name)
        except (KeyError, ValueError) as e:
            logger.error("Skipping invalid rule '%s': %s", entry.get("name", "?"), e)

    logger.info("Loaded %d rules from %s", len(rule_set.rules), path)
    return rule_set
