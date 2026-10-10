"""Turn a Markdown template into a final prompt using row values."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.errors import TemplateError

VARIABLE_PATTERN = re.compile(r"\{([A-Za-z0-9_]+)\}")


def extract_variables(template: str) -> set[str]:
    """Return the set of ``{variable}`` names found in the template."""
    return set(VARIABLE_PATTERN.findall(template))


@dataclass
class TemplateValidation:
    missing_columns: list[str]
    unused_columns: list[str]

    @property
    def ok(self) -> bool:
        return not self.missing_columns


def validate_template(template: str, columns: list[str]) -> TemplateValidation:
    """Compare template variables against available CSV columns."""
    variables = extract_variables(template)
    available = set(columns)
    missing = sorted(variables - available)
    unused = [column for column in columns if column not in variables]
    return TemplateValidation(missing_columns=missing, unused_columns=unused)


def render(template: str, values: dict[str, str]) -> str:
    """Replace ``{name}`` placeholders using values.

    Only placeholders matching valid variable names are replaced; any other
    braces in the Markdown text are left untouched. A placeholder without a
    matching value raises TemplateError instead of being silently ignored.
    """

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise TemplateError(f"Missing value for template variable: {{{name}}}")
        return values[name]

    return VARIABLE_PATTERN.sub(_replace, template)
