import re

import webhook_inbox


def test_version_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", webhook_inbox.__version__)
