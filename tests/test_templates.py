import pytest

from blender_mcp import templates


def test_every_template_is_described():
    assert set(templates.describe_templates()) == set(templates.TEMPLATES)


@pytest.mark.parametrize("name", sorted(templates.TEMPLATES))
def test_templates_are_syntactically_valid_python(name):
    compile(templates.get_template(name), f"<{name}>", "exec")


@pytest.mark.parametrize("name", sorted(templates.TEMPLATES))
def test_every_template_reports_a_result(name):
    assert "result =" in templates.get_template(name)


def test_unknown_template_lists_the_real_ones():
    with pytest.raises(ValueError, match="studio"):
        templates.get_template("no-such-template")
