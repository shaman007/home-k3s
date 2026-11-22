"""Prepare the separate OpenBao bundle in memory; never read/write or print secrets."""

import copy


def upgrade(bundle, *, voice_memory, memory_summary, memory_context_prefix,
            remember_description, key_description, content_description):
    """Accept operator-supplied texts without baking production prompts into the image."""
    # Keep each required secret text explicit; silently omitted fields break rollout.
    # pylint: disable=too-many-arguments
    texts = (voice_memory, memory_summary, memory_context_prefix,
             remember_description, key_description, content_description)
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("All memory prompt texts must be supplied")
    result = copy.deepcopy(bundle)
    result["voice"] += "\n" + voice_memory
    result["memory_summary"] = memory_summary
    result["memory_context_prefix"] = memory_context_prefix
    result["tools"]["remember_memory"] = {
        "/description": remember_description,
        "/parameters/properties/key/description": key_description,
        "/parameters/properties/content/description": content_description,
    }
    return result
