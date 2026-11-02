import json
from unittest.mock import Mock, patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from music.ai_engine import (
    generate_content_with_fallback,
    generate_playlist_content_with_fallback,
)


class GeminiFallbackTests(TestCase):
    @patch('music.ai_engine.GEMINI_MODELS', ['gemini-primary', 'gemini-backup'])
    def test_temporary_model_error_uses_next_model(self):
        client = Mock()
        response = Mock()
        client.models.generate_content.side_effect = [
            RuntimeError('503 Service Unavailable'),
            response
        ]

        result = generate_content_with_fallback(client, 'prompt', {})

        self.assertIs(result, response)
        self.assertEqual(
            [call.kwargs['model'] for call in client.models.generate_content.call_args_list],
            ['gemini-primary', 'gemini-backup']
        )

    @patch('music.ai_engine.GEMINI_MODELS', ['gemini-primary', 'gemini-backup'])
    def test_non_temporary_model_error_is_not_retried(self):
        client = Mock()
        client.models.generate_content.side_effect = RuntimeError('Invalid API key')

        with self.assertRaisesRegex(RuntimeError, 'Invalid API key'):
            generate_content_with_fallback(client, 'prompt', {})

        client.models.generate_content.assert_called_once()

    @patch('music.ai_engine.get_groq_api_key', return_value='test-groq-key')
    @patch('music.ai_engine.generate_content_with_fallback', side_effect=RuntimeError('Gemini unavailable'))
    @patch('music.ai_engine.requests.post')
    def test_groq_generates_playlist_when_gemini_fails(self, mock_post, mock_gemini, mock_key):
        response = Mock()
        response.json.return_value = {
            'choices': [{'message': {'content': '{"songs": []}'}}]
        }
        mock_post.return_value = response

        result = generate_playlist_content_with_fallback(Mock(), 'prompt', {})

        self.assertEqual(result.text, '{"songs": []}')
        mock_post.assert_called_once_with(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={'Authorization': 'Bearer test-groq-key'},
            json={
                'model': 'openai/gpt-oss-120b',
                'messages': [{'role': 'user', 'content': 'prompt'}],
                'response_format': {'type': 'json_object'}
            },
            timeout=30
        )


@override_settings(GEMINI_API_KEY='dummy-gemini-key', YOUTUBE_API_KEY='dummy-youtube-key')
class PlaylistGenerationErrorTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.client.cookies['moodtune_session_id'] = 'test-gemini-fallback-session'

    @patch('music.views.get_mood_playlist', return_value=None)
    def test_temporary_ai_failure_returns_retry_message(self, mock_get_playlist):
        response = self.client.post(
            reverse('generate_playlist'),
            data=json.dumps({'mood_text': 'relaxed'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()['message'],
            'The AI is busy right now. Please try again in a few seconds.'
        )
        mock_get_playlist.assert_called_once()
