"""House rules that stay in code.

`main` is the demo. These checks run on `sdd/factory` and on request branches.
The pull request base is `sdd/factory`.
"""

from pathlib import Path

from triage.contract import LabelSource

ROOT = Path(__file__).resolve().parent.parent
LABEL_SOURCES = {"model", "model_retry", "fallback", "skipped"}


def test_label_source_is_four_values():
    assert {item.value for item in LabelSource} == LABEL_SOURCES


def test_unclear_is_not_in_the_prompt():
    text = (ROOT / "triage" / "prompts.py").read_text()
    assert "unclear" not in text


def test_connect_does_not_set_a_category():
    for path in (ROOT / "connect").rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(errors="replace")
        assert "category:" not in text
        assert '"category"' not in text
