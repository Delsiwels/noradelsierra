"""Tests for streaming functionality."""

import json
import pytest
from unittest.mock import MagicMock, patch

from webapp.ai.models import StreamChunk
from webapp.ai.client import MockAIClient


class TestStreamChunk:
    """Tests for StreamChunk dataclass."""

    def test_stream_chunk_defaults(self):
        """Test StreamChunk default values."""
        chunk = StreamChunk(content="Hello")

        assert chunk.content == "Hello"
        assert chunk.done is False
        assert chunk.model == ""
        assert chunk.usage == {}
        assert chunk.skills_used == []
        assert chunk.error is None

    def test_stream_chunk_with_all_fields(self):
        """Test StreamChunk with all fields set."""
        chunk = StreamChunk(
            content="",
            done=True,
            model="test-model",
            usage={"input": 10, "output": 20},
            skills_used=["tax_agent"],
            error="Test error",
        )

        assert chunk.done is True
        assert chunk.model == "test-model"
        assert chunk.usage["input"] == 10
        assert chunk.skills_used == ["tax_agent"]
        assert chunk.error == "Test error"


class TestMockAIClientStreaming:
    """Tests for MockAIClient streaming."""

    def test_stream_chat_yields_chunks(self):
        """Test that stream_chat yields StreamChunk objects."""
        client = MockAIClient(response_content="Hello world")

        chunks = list(client.stream_chat([{"role": "user", "content": "Hi"}]))

        assert len(chunks) >= 2  # At least one word chunk + final
        assert all(isinstance(c, StreamChunk) for c in chunks)

    def test_stream_chat_accumulates_content(self):
        """Test that stream content accumulates correctly."""
        client = MockAIClient(response_content="Hello world test")

        chunks = list(client.stream_chat([{"role": "user", "content": "Hi"}]))

        # Get all content chunks (not done)
        content_chunks = [c for c in chunks if not c.done]
        content = "".join(c.content for c in content_chunks)

        assert "Hello" in content
        assert "world" in content

    def test_stream_chat_final_chunk(self):
        """Test final chunk has done=True and usage."""
        client = MockAIClient(response_content="Test response")

        chunks = list(client.stream_chat([{"role": "user", "content": "Hi"}]))

        final = [c for c in chunks if c.done]
        assert len(final) == 1
        assert final[0].usage == {"input": 10, "output": 20}

    def test_stream_chat_records_history(self):
        """Test that streaming calls are recorded."""
        client = MockAIClient()

        list(client.stream_chat(
            [{"role": "user", "content": "Hi"}],
            system_prompt="Be helpful",
        ))

        assert len(client.call_history) == 1
        assert client.call_history[0]["streaming"] is True
        assert client.call_history[0]["system_prompt"] == "Be helpful"


class TestStreamingEndpoint:
    """Tests for the streaming chat endpoint."""

    def test_stream_endpoint_returns_sse(self, client, app):
        """Test that stream endpoint returns SSE format."""
        from webapp.ai import init_ai_client, init_chat_service

        init_ai_client(app)
        init_chat_service(app)

        response = client.post(
            "/api/chat/stream",
            json={"message": "Hello"},
            headers={"Accept": "text/event-stream"},
        )

        assert response.status_code == 200
        assert response.content_type.startswith("text/event-stream")

    def test_stream_endpoint_yields_chunks(self, client, app):
        """Test that stream endpoint yields event chunks."""
        from webapp.ai import init_ai_client, init_chat_service

        init_ai_client(app)
        init_chat_service(app)

        response = client.post(
            "/api/chat/stream",
            json={"message": "Hello"},
        )

        data = response.get_data(as_text=True)

        # Should contain event: chunk
        assert "event: chunk" in data
        assert "data:" in data

    def test_stream_endpoint_final_chunk_has_metadata(self, client, app):
        """Test that final chunk includes skills and usage."""
        from webapp.ai import init_ai_client, init_chat_service

        init_ai_client(app)
        init_chat_service(app)

        response = client.post(
            "/api/chat/stream",
            json={"message": "Hello"},
        )

        data = response.get_data(as_text=True)
        lines = data.strip().split("\n")

        # Find data lines
        data_lines = [l for l in lines if l.startswith("data:")]

        # At least one should have done: true
        found_done = False
        for line in data_lines:
            parsed = json.loads(line.replace("data: ", ""))
            if parsed.get("done"):
                found_done = True
                assert "skills_used" in parsed
                assert "usage" in parsed

        assert found_done

    def test_stream_endpoint_requires_message(self, client):
        """Test that message is required."""
        response = client.post(
            "/api/chat/stream",
            json={"other": "field"},  # Provide JSON but no message
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "Message is required" in data["error"]

    def test_stream_endpoint_validates_history(self, client):
        """Test that history format is validated."""
        response = client.post(
            "/api/chat/stream",
            json={
                "message": "Hello",
                "history": "invalid",
            },
        )

        assert response.status_code == 400

    def test_stream_endpoint_with_persist(self, client, app):
        """Test streaming with persistence enabled."""
        from webapp.ai import init_ai_client, init_chat_service

        init_ai_client(app)
        init_chat_service(app)

        # Need a user_id for persistence to work
        # In testing mode without auth, persist won't actually work
        response = client.post(
            "/api/chat/stream",
            json={
                "message": "Hello",
                "persist": True,
            },
        )

        assert response.status_code == 200

    def test_stream_endpoint_service_unavailable(self, client, app):
        """Test response when chat service is not available."""
        import webapp.ai.chat_service as chat_module

        chat_module._chat_service = None

        response = client.post(
            "/api/chat/stream",
            json={"message": "Hello"},
        )

        assert response.status_code == 503


class TestChatServiceStreaming:
    """Tests for ChatService streaming method."""

    def test_send_message_stream_yields_chunks(self, app):
        """Test that send_message_stream yields chunks."""
        from webapp.ai import get_chat_service

        service = get_chat_service()

        chunks = list(service.send_message_stream("Hello"))

        assert len(chunks) >= 1
        assert all(isinstance(c, StreamChunk) for c in chunks)

    def test_send_message_stream_final_has_skills(self, app):
        """Test that final chunk includes skills_used."""
        from webapp.ai import get_chat_service

        service = get_chat_service()

        chunks = list(service.send_message_stream("Hello"))

        final = [c for c in chunks if c.done]
        assert len(final) == 1
        assert isinstance(final[0].skills_used, list)

    def test_send_message_stream_with_history(self, app):
        """Test streaming with conversation history."""
        from webapp.ai import get_chat_service

        service = get_chat_service()

        history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]

        chunks = list(service.send_message_stream(
            "How are you?",
            conversation_history=history,
        ))

        assert len(chunks) >= 1
