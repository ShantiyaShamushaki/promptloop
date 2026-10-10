from __future__ import annotations

import pytest

from app.errors import TemplateError
from app.template_engine import extract_variables, render, validate_template


def test_extract_variables():
    template = "Company: {company}\nCountry: {country}\n{nothing else}"
    assert extract_variables(template) == {"company", "country"}


def test_extract_variables_ignores_non_variable_braces():
    assert extract_variables("Use {'key': 1} and { a } here") == set()


def test_render_replaces_values():
    template = "Company: {company}\nCountry: {country}"
    result = render(template, {"company": "NVIDIA", "country": "USA"})
    assert result == "Company: NVIDIA\nCountry: USA"


def test_render_leaves_literal_braces_untouched():
    template = "JSON example: {'key': 1}\nCompany: {company}"
    result = render(template, {"company": "NVIDIA"})
    assert result == "JSON example: {'key': 1}\nCompany: NVIDIA"


def test_render_missing_value_raises():
    with pytest.raises(TemplateError):
        render("Company: {company}", {})


def test_validate_reports_missing_and_unused():
    validation = validate_template(
        "Company: {company}\nIndustry: {industry}",
        ["company", "country"],
    )
    assert validation.ok is False
    assert validation.missing_columns == ["industry"]
    assert validation.unused_columns == ["country"]


def test_validate_passes_when_all_variables_present():
    validation = validate_template("{company} {country}", ["company", "country"])
    assert validation.ok is True
    assert validation.missing_columns == []
    assert validation.unused_columns == []
