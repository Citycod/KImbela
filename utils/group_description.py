"""Shared sanitization for group descriptions stored as rich HTML."""

import bleach


GROUP_DESCRIPTION_TAGS = [
    "p",
    "br",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "ul",
    "ol",
    "li",
    "blockquote",
    "h2",
    "h3",
    "h4",
    "a",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
]

GROUP_DESCRIPTION_ATTRIBUTES = {
    "a": ["href", "target", "rel"],
    "table": ["border", "cellpadding", "cellspacing"],
    "th": ["colspan", "rowspan"],
    "td": ["colspan", "rowspan"],
}


def sanitize_group_description(raw_description):
    cleaned = bleach.clean(
        raw_description or "",
        tags=GROUP_DESCRIPTION_TAGS,
        attributes=GROUP_DESCRIPTION_ATTRIBUTES,
        strip=True,
    ).strip()
    plain_text = bleach.clean(cleaned, tags=[], strip=True).strip()
    return cleaned if plain_text else ""
