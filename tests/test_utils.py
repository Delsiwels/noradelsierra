"""Tests for utility functions."""

from webapp.utils import sanitize_input, validate_email


class TestValidateEmail:
    """Tests for validate_email function."""

    def test_valid_email(self):
        assert validate_email("user@example.com") is True
        assert validate_email("test.user@domain.org") is True

    def test_invalid_email(self):
        assert validate_email("invalid") is False
        assert validate_email("@example.com") is False
        assert validate_email("user@") is False


class TestSanitizeInput:
    """Tests for sanitize_input function."""

    def test_removes_html_tags(self):
        result = sanitize_input("<script>alert('xss')</script>")
        assert "<" not in result
        assert ">" not in result

    def test_empty_string(self):
        assert sanitize_input("") == ""

    def test_non_string_input(self):
        assert sanitize_input(123) == ""
