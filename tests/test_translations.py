"""The translation files must stay in step with strings.json."""

import json
from pathlib import Path

COMPONENT = Path(__file__).parents[1] / "custom_components" / "brink_flair"


def test_english_translations_match_strings() -> None:
    """translations/en.json is a copy of strings.json, so both must agree."""
    strings = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
    english = json.loads(
        (COMPONENT / "translations" / "en.json").read_text(encoding="utf-8")
    )
    assert english == strings
