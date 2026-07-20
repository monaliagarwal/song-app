import json
import uuid
import os
import logging
import time
import io
from PIL import Image
from datetime import timedelta
from django.utils import timezone
from google import genai
from google.genai import types
from google.genai import errors
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from .models import Playlist, Song, MoodHistory
from .ai_engine import get_mood_playlist, search_songs, save_to_cloud, GCS_AVAILABLE, GCS_BUCKET_NAME

logger = logging.getLogger('moodtune')

# Helper function to get or generate session ID
def get_session_id(request):
    return request.COOKIES.get('moodtune_session_id')

@ensure_csrf_cookie
def index_view(request):
    """
    Renders player.html and handles session identification cookie setup.
    """
    session_id = get_session_id(request)
    new_session = False
    if not session_id:
        session_id = str(uuid.uuid4())
        new_session = True

    # Check if '?room=' query parameter is present, otherwise default to session_id
    room_id = request.GET.get('room', '').strip()
    if not room_id:
        room_id = session_id

    # Load user's playlists and mood histories
    playlists = Playlist.objects.filter(session_id=session_id).order_by('-created_at')
    mood_histories = MoodHistory.objects.filter(session_id=session_id).order_by('-created_at')[:5]

    response = render(request, 'music/player.html', {
        'playlists': playlists,
        'mood_histories': mood_histories,
        'session_id': session_id,
        'room_id': room_id,
    })

    if new_session:
        # Set session ID cookie for 1 year
        response.set_cookie('moodtune_session_id', session_id, max_age=365 * 24 * 60 * 60, httponly=True)

    return response

@require_http_methods(["POST"])
def generate_playlist_view(request):
    """
    Generates a playlist using AI recommendations based on user mood and language choice.
    """
    view_start = time.time()
    gemini_time = 0.0
    youtube_time = 0.0
    embed_check_time = 0.0
    db_time = 0.0
    try:
        session_id = get_session_id(request)
        if not session_id:
            return JsonResponse({'status': 'error', 'message': 'Session expired'}, status=400)

        data = json.loads(request.body)
        mood_text = data.get('mood_text', '').strip()
        language_preference = data.get('language_preference', 'mix').strip()

        if not mood_text:
            return JsonResponse({'status': 'error', 'message': 'Mood description is required'}, status=400)

        from .ai_engine import get_gemini_api_key, get_youtube_api_key
        if not get_gemini_api_key():
            return JsonResponse({'status': 'error', 'message': 'gemini_api environment variable is not set on Render.'}, status=400)
        if not get_youtube_api_key():
            return JsonResponse({'status': 'error', 'message': 'youtube_api environment variable is not set on Render.'}, status=400)

        # Decorate mood text with language preference for Gemini prompt
        gemini_prompt = mood_text
        if language_preference and language_preference != 'mix':
            gemini_prompt += f" (Note: Please recommend songs primarily in {language_preference} language)"
        elif language_preference == 'mix':
            gemini_prompt += " (Note: Recommend a mix of Hindi and English songs)"

        # Check if same mood was searched in last 24 hours in MoodHistory database
        time_threshold = timezone.now() - timedelta(hours=24)
        existing_history = MoodHistory.objects.filter(
            mood_text__iexact=mood_text,
            created_at__gte=time_threshold
        ).select_related('playlist').order_by('-created_at').first()

        if existing_history and existing_history.playlist:
            db_start = time.time()
            cached_playlist = existing_history.playlist
            
            # Clone the playlist for the current session
            playlist = Playlist.objects.create(
                name=cached_playlist.name,
                session_id=session_id,
                mood=cached_playlist.mood
            )
            
            # Clone all songs
            songs_response = []
            for song in cached_playlist.songs.all().order_by('order'):
                new_song = Song.objects.create(
                    playlist=playlist,
                    title=song.title,
                    artist=song.artist,
                    youtube_id=song.youtube_id,
                    thumbnail=song.thumbnail,
                    duration=song.duration,
                    order=song.order
                )
                songs_response.append({
                    'id': new_song.id,
                    'title': new_song.title,
                    'artist': new_song.artist,
                    'youtube_id': new_song.youtube_id,
                    'thumbnail': new_song.thumbnail,
                    'duration': new_song.duration,
                    'order': new_song.order,
                    'is_favorite': False
                })
                
            # Create MoodHistory entry for current session
            history = MoodHistory.objects.create(
                session_id=session_id,
                mood_text=mood_text,
                playlist=playlist
            )
            db_time = time.time() - db_start

            total_time = time.time() - view_start
            logger.info(f"""
TIMING BREAKDOWN:
- Gemini call: {gemini_time:.2f}s
- YouTube searches: {youtube_time:.2f}s  
- Embeddable checks: {embed_check_time:.2f}s
- Database saves: {db_time:.2f}s
- TOTAL: {total_time:.2f}s
""")
            
            return JsonResponse({
                'status': 'success',
                'playlist': {
                    'id': playlist.id,
                    'name': playlist.name,
                    'mood': playlist.mood,
                    'songs_count': playlist.songs.count()
                },
                'history': {
                    'id': history.id,
                    'playlist_id': playlist.id,
                    'mood_text': history.mood_text
                },
                'songs': songs_response
            })

        # Generate playlist recommendations
        playlist_data = get_mood_playlist(gemini_prompt)
        if not playlist_data:
            return JsonResponse({'status': 'error', 'message': 'AI could not process mood request. Please verify API configurations.'}, status=500)

        # Extract timing metrics if they exist
        gemini_time = playlist_data.get('gemini_time', 0.0)
        youtube_time = playlist_data.get('youtube_time', 0.0)
        embed_check_time = playlist_data.get('embed_check_time', 0.0)

        db_start = time.time()
        playlist_name = playlist_data.get('playlist_name', 'Mood Playlist')
        mood_analysis = playlist_data.get('mood_analysis', '')
        songs_list = playlist_data.get('songs', [])

        # Create Playlist object
        playlist = Playlist.objects.create(
            name=playlist_name,
            session_id=session_id,
            mood=mood_analysis
        )

        # Create Song objects
        songs_response = []
        for index, song in enumerate(songs_list):
            new_song = Song.objects.create(
                playlist=playlist,
                title=song.get('title', 'Unknown Title'),
                artist=song.get('artist', 'Unknown Artist'),
                youtube_id=song.get('youtube_id', ''),
                thumbnail=song.get('thumbnail', ''),
                duration='3:30', # Default duration
                order=index
            )
            songs_response.append({
                'id': new_song.id,
                'title': new_song.title,
                'artist': new_song.artist,
                'youtube_id': new_song.youtube_id,
                'thumbnail': new_song.thumbnail,
                'duration': new_song.duration,
                'order': new_song.order,
                'is_favorite': False
            })

        # Create MoodHistory entry
        history = MoodHistory.objects.create(
            session_id=session_id,
            mood_text=mood_text,
            playlist=playlist
        )

        # Backup playlist and mood history to Google Cloud Storage
        try:
            if GCS_AVAILABLE and GCS_BUCKET_NAME:
                save_to_cloud(session_id, playlist_data, mood_text)
        except Exception:
            pass
        db_time = time.time() - db_start

        total_time = time.time() - view_start
        logger.info(f"""
TIMING BREAKDOWN:
- Gemini call: {gemini_time:.2f}s
- YouTube searches: {youtube_time:.2f}s  
- Embeddable checks: {embed_check_time:.2f}s
- Database saves: {db_time:.2f}s
- TOTAL: {total_time:.2f}s
""")

        return JsonResponse({
            'status': 'success',
            'playlist': {
                'id': playlist.id,
                'name': playlist.name,
                'mood': playlist.mood,
                'songs_count': playlist.songs.count()
            },
            'history': {
                'id': history.id,
                'playlist_id': playlist.id,
                'mood_text': history.mood_text
            },
            'songs': songs_response
        })

    except Exception as e:
        total_time = time.time() - view_start
        logger.info(f"""
TIMING BREAKDOWN:
- Gemini call: {gemini_time:.2f}s
- YouTube searches: {youtube_time:.2f}s  
- Embeddable checks: {embed_check_time:.2f}s
- Database saves: {db_time:.2f}s
- TOTAL: {total_time:.2f}s
""")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def search_view(request):
    """
    Searches YouTube music videos.
    """
    try:
        from .ai_engine import get_youtube_api_key
        if not get_youtube_api_key():
            return JsonResponse({'status': 'error', 'message': 'youtube_api environment variable is not set on Render.'}, status=400)

        query = request.GET.get('q', '').strip()
        if not query:
            return JsonResponse({'status': 'success', 'songs': []})

        results = search_songs(query)
        if results is None:
            return JsonResponse({'status': 'error', 'message': 'Search failed. Please check YouTube API key or quota.'}, status=500)

        return JsonResponse({'status': 'success', 'songs': results})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_http_methods(["POST"])
def create_playlist_view(request):
    """
    Creates an empty playlist.
    """
    try:
        session_id = get_session_id(request)
        if not session_id:
            return JsonResponse({'status': 'error', 'message': 'Session expired'}, status=400)

        data = json.loads(request.body)
        name = data.get('name', '').strip() or 'New Playlist'

        playlist = Playlist.objects.create(
            name=name,
            session_id=session_id,
            mood="Custom Playlist"
        )

        return JsonResponse({
            'status': 'success',
            'playlist': {
                'id': playlist.id,
                'name': playlist.name,
                'songs_count': 0
            }
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_http_methods(["POST"])
def add_song_view(request):
    """
    Adds a song to the specified playlist.
    """
    try:
        data = json.loads(request.body)
        playlist_id = data.get('playlist_id') or active_playlist_id_resolver(request)
        youtube_id = data.get('youtube_id', '').strip()
        title = data.get('title', '').strip()
        artist = data.get('artist', '').strip()
        thumbnail = data.get('thumbnail', '').strip()
        duration = data.get('duration', '3:30').strip()

        if not playlist_id:
            return JsonResponse({'status': 'error', 'message': 'Playlist ID is required'}, status=400)
        if not youtube_id:
            return JsonResponse({'status': 'error', 'message': 'YouTube ID is required'}, status=400)

        playlist = Playlist.objects.get(id=playlist_id)
        
        # Calculate order
        next_order = Song.objects.filter(playlist=playlist).count()

        song = Song.objects.create(
            playlist=playlist,
            title=title or 'Unknown Title',
            artist=artist or 'Unknown Artist',
            youtube_id=youtube_id,
            thumbnail=thumbnail,
            duration=duration,
            order=next_order
        )

        return JsonResponse({
            'status': 'success',
            'playlist_name': playlist.name,
            'song': {
                'id': song.id,
                'title': song.title,
                'artist': song.artist,
                'youtube_id': song.youtube_id,
                'thumbnail': song.thumbnail,
                'duration': song.duration,
                'order': song.order,
                'is_favorite': False
            }
        })
    except Playlist.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Playlist not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# Helper to find playlist ID when posting direct song cards
def active_playlist_id_resolver(request):
    # Try fetching playlist ID from headers or request path
    return None

@require_http_methods(["POST"])
def remove_song_view(request):
    """
    Removes a song from database by ID.
    """
    try:
        data = json.loads(request.body)
        song_id = data.get('song_id')

        if not song_id:
            return JsonResponse({'status': 'error', 'message': 'Song ID is required'}, status=400)

        song = Song.objects.get(id=song_id)
        playlist = song.playlist
        song.delete()

        # Recalculate remaining song orders to keep indexing clean
        songs = Song.objects.filter(playlist=playlist).order_by('order')
        for index, s in enumerate(songs):
            s.order = index
            s.save()

        return JsonResponse({'status': 'success'})
    except Song.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Song not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_http_methods(["POST"])
def delete_playlist_view(request):
    """
    Deletes playlist and cascade deletes its songs.
    """
    try:
        # Check both JSON parameter and URL parameter fallback
        data = json.loads(request.body) if request.body else {}
        playlist_id = data.get('playlist_id')

        if not playlist_id:
            return JsonResponse({'status': 'error', 'message': 'Playlist ID is required'}, status=400)

        playlist = Playlist.objects.get(id=playlist_id)
        playlist.delete()

        return JsonResponse({'status': 'success'})
    except Playlist.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Playlist not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def get_playlist_view(request, playlist_id):
    """
    Retrieves all songs belonging to a playlist.
    """
    try:
        playlist = Playlist.objects.get(id=playlist_id)
        songs = Song.objects.filter(playlist=playlist).order_by('order')
        
        songs_data = []
        for song in songs:
            songs_data.append({
                'id': song.id,
                'title': song.title,
                'artist': song.artist,
                'youtube_id': song.youtube_id,
                'thumbnail': song.thumbnail,
                'duration': song.duration,
                'order': song.order,
                'is_favorite': False # Placeholder for favorite logic
            })

        return JsonResponse({
            'status': 'success',
            'playlist': {
                'id': playlist.id,
                'name': playlist.name,
                'mood': playlist.mood
            },
            'songs': songs_data
        })
    except Playlist.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Playlist not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_http_methods(["POST"])
def update_name_view(request, playlist_id):
    """
    Updates the name of a playlist.
    """
    try:
        playlist = Playlist.objects.get(id=playlist_id)
        data = json.loads(request.body)
        new_name = data.get('name', '').strip()

        if not new_name:
            return JsonResponse({'status': 'error', 'message': 'Playlist name is required'}, status=400)

        playlist.name = new_name
        playlist.save()

        return JsonResponse({'status': 'success'})
    except Playlist.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Playlist not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_http_methods(["POST"])
def reorder_songs_view(request, playlist_id):
    """
    Saves the new sorting order of playlist songs.
    """
    try:
        playlist = Playlist.objects.get(id=playlist_id)
        data = json.loads(request.body)
        song_ids = data.get('song_ids', [])

        if not song_ids:
            return JsonResponse({'status': 'error', 'message': 'Song IDs array is required'}, status=400)

        # Update order field for each song
        for index, song_id in enumerate(song_ids):
            Song.objects.filter(id=song_id, playlist=playlist).update(order=index)

        return JsonResponse({'status': 'success'})
    except Playlist.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Playlist not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


def detect_mood(image_data):
    """
    Helper function to process image data and call Gemini Vision API.
    """
    import base64
    from PIL import Image

    # Fetch API key from settings or environment
    from .ai_engine import get_gemini_api_key
    api_key = get_gemini_api_key()

    if not api_key:
        raise ValueError('gemini_api environment variable is not set on Render.')

    client = genai.Client(api_key=api_key)

    img_bytes = base64.b64decode(image_data)

    # Compress and resize image using Pillow
    try:
        image = Image.open(io.BytesIO(img_bytes))
        # Convert to RGB mode if it's in RGBA/LA/P mode to allow JPEG save
        if image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGB')
        # Calculate new size keeping aspect ratio with max 800px on the longest side
        max_size = 800
        width, height = image.size
        if width > max_size or height > max_size:
            if width > height:
                new_width = max_size
                new_height = int(height * (max_size / width))
            else:
                new_height = max_size
                new_width = int(width * (max_size / height))
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        # Re-encode as JPEG quality=80
        out_bytes_io = io.BytesIO()
        image.save(out_bytes_io, format='JPEG', quality=80)
        img_bytes = out_bytes_io.getvalue()
    except Exception as img_err:
        logger.warning(f"Selfie compression failed: {img_err}. Proceeding with original bytes.")

    prompt = """Look at this person's face carefully.
Analyse their facial expression, eyes, and overall appearance.

Detect their current emotional state and return ONLY this JSON:
{
  "mood": "one word mood (happy/sad/stressed/tired/excited/angry/calm/anxious)",
  "confidence": "percentage like 87%",
  "face_analysis": "one fun sentence about what you see",
  "energy_level": "high/medium/low"
}

Be accurate but fun. No extra text, only JSON."""

    # Send image to Gemini using the new Client syntax, wrapped in timeout
    gemini_start = time.time()
    api_name = "Gemini Vision mood detection"
    try:
        def make_vision_call():
            return client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type='image/jpeg'),
                    prompt
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(make_vision_call)
            response = future.result(timeout=30)

        logger.info(f"API_CALL_SUCCESS: {api_name} took {time.time()-gemini_start:.2f}s")
    except Exception as e:
        if isinstance(e, TimeoutError):
            logger.error(f"API_CALL_FAILED: {api_name} error: Network timeout (Gemini call timed out after 30s) took {time.time()-gemini_start:.2f}s")
        elif isinstance(e, errors.APIError):
            if e.code == 429:
                logger.error(f"GEMINI_API_RATE_LIMIT (429): {api_name} error: rate limit hit took {time.time()-gemini_start:.2f}s")
            logger.error(f"API_CALL_FAILED: {api_name} error: APIError {e.code} - {e.message} took {time.time()-gemini_start:.2f}s")
        else:
            logger.error(f"API_CALL_FAILED: {api_name} error: {str(e)} took {time.time()-gemini_start:.2f}s")
        raise

    raw_text = response.text.strip()

    # Handle markdown blocks ```json ... ``` robustly if they exist
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines[-1].startswith("```"):
            lines = lines[:-1]
        raw_text = "\n".join(lines).strip()

    return json.loads(raw_text)


@require_http_methods(["POST"])
def detect_mood_view(request):
    """
    Receives a base64-encoded image, calls Gemini Vision API to analyze facial expressions,
    and returns detected mood and analysis data in JSON format.
    """
    try:
        from .ai_engine import get_gemini_api_key
        if not get_gemini_api_key():
            return JsonResponse({'status': 'error', 'message': 'gemini_api environment variable is not set on Render.'}, status=400)

        data = json.loads(request.body)
        image_data = data.get('image', '').strip()

        if not image_data:
            return JsonResponse({'status': 'error', 'message': 'No image data provided'}, status=400)

        # Strip prefix if it's a data URL (e.g. "data:image/jpeg;base64,...")
        if ',' in image_data:
            image_data = image_data.split(',', 1)[1]

        try:
            result = detect_mood(image_data)
        except Exception as e:
            import traceback
            print(f"DETECT MOOD ERROR: {traceback.format_exc()}")
            return JsonResponse({'error': str(e)}, status=500)

        return JsonResponse({
            'status': 'success',
            'data': result
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


