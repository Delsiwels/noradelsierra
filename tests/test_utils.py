"""Tests for utility functions."""

from webapp.utils import hash_password, paginate, sanitize_input, validate_email


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


class TestHashPassword:
    """Tests for hash_password function."""

    def test_returns_hash(self):
        result = hash_password("password123")
        assert len(result) == 64  # SHA-256 produces 64 hex chars

    def test_same_input_same_hash(self):
        hash1 = hash_password("test")
        hash2 = hash_password("test")
        assert hash1 == hash2


class TestPaginate:
    """Tests for paginate function."""

    def test_basic_pagination(self):
        items = list(range(10))
        result = paginate(items, page=1, per_page=3)

        assert result["items"] == [0, 1, 2]
        assert result["page"] == 1
        assert result["total"] == 10
        assert result["pages"] == 4

    def test_last_page(self):
        items = list(range(10))
        result = paginate(items, page=4, per_page=3)

        assert result["items"] == [9]
