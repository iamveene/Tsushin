"""
Tests for XSS and HTML injection fixes (BUG-056, BUG-063).

Validates that:
1. _create_snippet HTML-escapes content before adding <mark> tags
2. _sanitize_sql_snippet preserves <mark> tags while escaping content
3. TonePreset name/description fields strip HTML tags
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# BUG-056: Stored XSS via search snippets
# ============================================================================

class TestCreateSnippetEscaping:
    """Test that _create_snippet HTML-escapes content before highlighting."""

    def _get_service(self):
        """Create a ConversationSearchService instance with a None db (not needed for snippet tests)."""
        from services.conversation_search_service import ConversationSearchService
        return ConversationSearchService(db=None)

    def test_script_tag_is_escaped(self):
        """XSS payload in content must be HTML-escaped in the snippet."""
        service = self._get_service()
        content = '<script>alert("xss")</script> keyword here'
        snippet = service._create_snippet(content, "keyword")

        assert "<script>" not in snippet
        assert "&lt;script&gt;" in snippet
        assert "<mark>keyword</mark>" in snippet

    def test_img_onerror_is_escaped(self):
        """img onerror XSS payload must be escaped."""
        service = self._get_service()
        content = '<img src=x onerror=alert(1)> search term found'
        snippet = service._create_snippet(content, "search term")

        assert "<img" not in snippet
        assert "&lt;img" in snippet
        assert "<mark>search term</mark>" in snippet

    def test_mark_tags_are_applied_after_escaping(self):
        """<mark> tags should wrap the matched query text."""
        service = self._get_service()
        content = "This is a normal text with the word hello in it"
        snippet = service._create_snippet(content, "hello")

        assert "<mark>hello</mark>" in snippet

    def test_no_match_returns_escaped_content(self):
        """When query is not found, snippet should still be HTML-escaped."""
        service = self._get_service()
        content = '<b>bold</b> & "quotes" everywhere'
        snippet = service._create_snippet(content, "nonexistent_query")

        assert "<b>" not in snippet
        assert "&lt;b&gt;" in snippet
        assert "&amp;" in snippet
        assert "&quot;" in snippet

    def test_query_with_html_chars(self):
        """Query containing HTML special chars should match on escaped text."""
        service = self._get_service()
        content = 'User typed <b>test</b> in the message'
        snippet = service._create_snippet(content, "<b>test</b>")

        # The query itself gets escaped, so it should match the escaped content
        assert "<mark>&lt;b&gt;test&lt;/b&gt;</mark>" in snippet

    def test_ampersand_in_content_is_escaped(self):
        """Ampersands in content must be properly escaped."""
        service = self._get_service()
        content = "Tom & Jerry found the keyword today"
        snippet = service._create_snippet(content, "keyword")

        assert "&amp;" in snippet
        assert "<mark>keyword</mark>" in snippet


class TestSanitizeSqlSnippet:
    """Test that _sanitize_sql_snippet preserves <mark> but escapes everything else."""

    def _get_method(self):
        from services.conversation_search_service import ConversationSearchService
        return ConversationSearchService._sanitize_sql_snippet

    def test_script_between_marks_is_escaped(self):
        """Content between <mark> tags must be escaped, <mark> tags preserved."""
        sanitize = self._get_method()
        raw = '<script>alert(1)</script>...<mark>keyword</mark>...more text'
        result = sanitize(raw)

        assert "<script>" not in result
        assert "&lt;script&gt;" in result
        assert "<mark>keyword</mark>" in result

    def test_preserves_multiple_mark_tags(self):
        """Multiple <mark> tags should all be preserved."""
        sanitize = self._get_method()
        raw = 'before <mark>first</mark> middle <mark>second</mark> after'
        result = sanitize(raw)

        assert result == 'before <mark>first</mark> middle <mark>second</mark> after'

    def test_escapes_angle_brackets_outside_marks(self):
        """Angle brackets outside <mark> tags must be escaped."""
        sanitize = self._get_method()
        raw = '<div>unsafe</div><mark>safe</mark>'
        result = sanitize(raw)

        assert "&lt;div&gt;unsafe&lt;/div&gt;" in result
        assert "<mark>safe</mark>" in result

    def test_empty_and_none_input(self):
        """Edge cases: empty string and None should be handled gracefully."""
        sanitize = self._get_method()
        assert sanitize("") == ""
        assert sanitize(None) is None


# ============================================================================
# BUG-063: Tone preset name/description lack HTML sanitization
# ============================================================================

class TestTonePresetSanitization:
    """Test that TonePreset models strip HTML from name and description."""

    def test_create_name_strips_script_tag(self):
        """Script tags in name should be stripped."""
        from api.routes_agents import TonePresetCreate

        preset = TonePresetCreate(
            name='<script>alert("xss")</script>Professional',
            description='A professional tone'
        )
        assert '<script>' not in preset.name
        assert 'Professional' in preset.name

    def test_create_description_strips_html(self):
        """HTML tags in description should be stripped."""
        from api.routes_agents import TonePresetCreate

        preset = TonePresetCreate(
            name='Friendly',
            description='<b>Bold</b> and <i>italic</i> tone'
        )
        assert '<b>' not in preset.description
        assert '<i>' not in preset.description
        assert 'Bold' in preset.description
        assert 'italic' in preset.description

    def test_create_name_empty_after_strip_raises(self):
        """Name that is only HTML tags should raise validation error."""
        from api.routes_agents import TonePresetCreate

        with pytest.raises(Exception):
            TonePresetCreate(
                name='<script></script>',
                description='Valid description'
            )

    def test_update_name_strips_html(self):
        """HTML tags in update name should be stripped."""
        from api.routes_agents import TonePresetUpdate

        preset = TonePresetUpdate(
            name='<img src=x onerror=alert(1)>CleanName'
        )
        assert '<img' not in preset.name
        assert 'CleanName' in preset.name

    def test_update_description_strips_html(self):
        """HTML tags in update description should be stripped."""
        from api.routes_agents import TonePresetUpdate

        preset = TonePresetUpdate(
            description='<a href="evil.com">Click here</a> for more info'
        )
        assert '<a' not in preset.description
        assert 'Click here' in preset.description
        assert 'for more info' in preset.description


# ============================================================================
# Sanitizer utility tests
# ============================================================================

class TestStripHtmlTags:
    """Test the strip_html_tags utility function."""

    def test_strips_basic_tags(self):
        from api.sanitizers import strip_html_tags
        assert strip_html_tags('<b>bold</b>') == 'bold'

    def test_strips_script_tags(self):
        from api.sanitizers import strip_html_tags
        assert strip_html_tags('<script>alert(1)</script>') == 'alert(1)'

    def test_preserves_plain_text(self):
        from api.sanitizers import strip_html_tags
        assert strip_html_tags('Hello World') == 'Hello World'

    def test_handles_empty_string(self):
        from api.sanitizers import strip_html_tags
        assert strip_html_tags('') == ''

    def test_handles_none(self):
        from api.sanitizers import strip_html_tags
        assert strip_html_tags(None) is None

    def test_strips_nested_tags(self):
        from api.sanitizers import strip_html_tags
        assert strip_html_tags('<div><p>text</p></div>') == 'text'

    def test_strips_self_closing_tags(self):
        from api.sanitizers import strip_html_tags
        assert strip_html_tags('before<br/>after') == 'beforeafter'
