"""Prepare action-policy and reminder-tool descriptions in memory, without secret I/O."""

import copy

DESCRIPTION_PATHS = {
    "update_daily_reminder": {"/description"},
    "suspend_daily_reminder": {"/description", "/parameters/properties/until_date/description"},
    "resume_daily_reminder": {"/description"},
}


def upgrade(bundle, *, policy, descriptions):
    """Keep production text external and constrain the migration to known text slots."""
    if not isinstance(policy, str) or not policy.strip() or not isinstance(descriptions, dict):
        raise ValueError("Action policy and tool descriptions are required")
    if set(descriptions) != set(DESCRIPTION_PATHS):
        raise ValueError("Unexpected reminder tool catalog")
    for name, paths in DESCRIPTION_PATHS.items():
        values = descriptions[name]
        if (not isinstance(values, dict) or set(values) != paths
                or any(not isinstance(text, str) or not text.strip() for text in values.values())):
            raise ValueError("Unexpected reminder description slots")
    result = copy.deepcopy(bundle)
    result["voice"] += "\n" + policy
    result["tools"].update(copy.deepcopy(descriptions))
    return result
