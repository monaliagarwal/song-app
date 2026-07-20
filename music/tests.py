import json
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from unittest.mock import patch

@override_settings(GROQ_API_KEY='dummy-groq-key', GEMINI_API_KEY='dummy-gemini-key', YOUTUBE_API_KEY='dummy-youtube-key')
class MusicAppTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Set session cookie to avoid empty session responses
        self.client.cookies['moodtune_session_id'] = 'test-session-uuid-12345'

    def test_index_view_returns_200(self):
        """Index page loads successfully and sets cookies."""
        url = reverse('index')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'music/player.html')
        self.assertIn('moodtune_session_id', self.client.cookies)

    @patch('music.views.get_mood_playlist')
    def test_generate_playlist_view_returns_valid_json(self, mock_get_playlist):
        """AI playlist generation returns 200 and exactly 8 song recommendations."""
        mock_get_playlist.return_value = {
            "mood_analysis": "Relaxing environment",
            "playlist_name": "Calm Study Vibe",
            "songs": [
                {
                    "title": f"Song {i}",
                    "artist": f"Artist {i}",
                    "youtube_id": f"yt_id_{i}",
                    "thumbnail": f"https://example.com/img{i}.jpg",
                    "duration": "3:00",
                    "order": i
                } for i in range(8)
            ]
        }

        url = reverse('generate_playlist')
        payload = {
            "mood_text": "relaxed and happy",
            "language_preference": "mix"
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertEqual(res_data['status'], 'success')
        self.assertEqual(len(res_data['songs']), 8)
        self.assertEqual(res_data['playlist']['name'], 'Calm Study Vibe')

    @patch('music.views.search_songs')
    def test_search_songs_view(self, mock_search):
        """Search view returns 200 and search results list."""
        mock_search.return_value = [
            {
                "youtube_id": "test_yt_123",
                "title": "Mocked Test Song",
                "artist": "Mocked Artist",
                "thumbnail": "https://example.com/thumb.jpg"
            }
        ]

        url = reverse('search')
        response = self.client.get(url, {'q': 'mocked search'})
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertEqual(res_data['status'], 'success')
        self.assertEqual(len(res_data['songs']), 1)
        self.assertEqual(res_data['songs'][0]['title'], 'Mocked Test Song')

    @patch('google.genai.Client')
    def test_detect_mood_view_handling(self, mock_genai_client):
        """Selfie mood detection handles dummy base64 captures without crashing."""
        # Mock Gemini Vision API response text
        mock_response = mock_genai_client.return_value.models.generate_content.return_value
        mock_response.text = json.dumps({
            "mood": "calm",
            "confidence": "90%",
            "face_analysis": "Expressing calm and relaxed features",
            "energy_level": "medium"
        })

        # Tiny base64 dummy JPEG encoding representation (1x1 transparent pixel)
        dummy_base64_image = "data:image/jpeg;base64,/9g/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="

        url = reverse('detect_mood')
        payload = {
            "image": dummy_base64_image
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertEqual(res_data['status'], 'success')
        self.assertEqual(res_data['data']['mood'], 'calm')
