"""
Rule Evaluator for Approval Matrix.
Evaluates configurable conditions against entity data to determine approval routing.
"""
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger(__name__)

# Supported operators
OPERATORS = {
    "EQ": lambda a, b: a == b,
    "NEQ": lambda a, b: a != b,
    "GT": lambda a, b: a > b,
    "GTE": lambda a, b: a >= b,
    "LT": lambda a, b: a < b,
    "LTE": lambda a, b: a <= b,
    "IN": lambda a, b: a in b,
    "NOT_IN": lambda a, b: a not in b,
    "CONTAINS": lambda a, b: b in str(a),
    "STARTS_WITH": lambda a, b: str(a).startswith(str(b)),
}


def _cast_value(value: str, data_type: str) -> Any:
    """Cast string value to appropriate type for comparison."""
    if data_type == "NUMBER":
        return Decimal(value)
    if data_type == "BOOLEAN":
        return value.lower() in ("true", "1", "yes")
    if data_type == "LIST":
        return [v.strip() for v in value.split(",")]
    return str(value)


def _get_entity_value(entity_data: dict, field: str) -> Any:
    """Get a value from entity data, supporting nested keys with dot notation."""
    keys = field.split(".")
    value = entity_data
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return None
    return value


class RuleEvaluator:
    """
    Evaluates approval rules against entity data.

    Rules are evaluated as AND within a logical group
    and OR between logical groups.
    """

    def evaluate_rules(self, rules: list[dict], entity_data: dict) -> bool:
        """
        Evaluate a set of rules against entity data.
        Returns True if ALL rules in ANY logical group match.
        """
        if not rules:
            return True

        # Group rules by logical_group
        groups: dict[str, list[dict]] = {}
        for rule in rules:
            group = rule.get("logical_group", "default")
            groups.setdefault(group, []).append(rule)

        # OR between groups (any group fully matching is sufficient)
        for group_name, group_rules in groups.items():
            if self._evaluate_group(group_rules, entity_data):
                return True

        return False

    def _evaluate_group(self, rules: list[dict], entity_data: dict) -> bool:
        """Evaluate all rules in a group (AND logic)."""
        for rule in rules:
            if not self.evaluate_single_rule(rule, entity_data):
                return False
        return True

    def evaluate_single_rule(self, rule: dict, entity_data: dict) -> bool:
        """Evaluate a single rule condition."""
        field = rule.get("field", "")
        operator = rule.get("operator", "EQ")
        value = rule.get("value", "")
        data_type = rule.get("data_type", "STRING")

        entity_value = _get_entity_value(entity_data, field)
        if entity_value is None:
            logger.debug("Field '%s' not found in entity data", field)
            return False

        try:
            compare_value = _cast_value(value, data_type)
            if data_type == "NUMBER" and not isinstance(entity_value, Decimal):
                entity_value = Decimal(str(entity_value))

            op_func = OPERATORS.get(operator)
            if not op_func:
                logger.warning("Unknown operator: %s", operator)
                return False

            result = op_func(entity_value, compare_value)
            logger.debug(
                "Rule eval: %s %s %s → %s", field, operator, value, result
            )
            return result
        except (ValueError, TypeError, InvalidOperation) as e:
            logger.error("Rule evaluation error: %s", e)
            return False
