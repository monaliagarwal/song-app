import os
import json
import requests
import logging
import time
from google import genai
from google.genai import errors
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

def get_groq_api_key():
    try:
        from django.conf import settings
        key = getattr(settings, 'GROQ_API_KEY', None)
        if key:
            return key
    except Exception:
        pass
    return os.environ.get('groq_api') or os.environ.get('GROQ_API_KEY')

def get_gemini_api_key():
    try:
        from django.conf import settings
        key = getattr(settings, 'GEMINI_API_KEY', None)
        if key:
            return key
    except Exception:
        pass
    return os.environ.get('gemini_api') or os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')

def get_youtube_api_key():
    try:
        from django.conf import settings
        key = getattr(settings, 'YOUTUBE_API_KEY', None)
        if key:
            return key
    except Exception:
        pass
    return os.environ.get('youtube_api') or os.environ.get('YOUTUBE_API_KEY') or os.environ.get('YOUTUBE_DATA_API_KEY')

def get_gcs_bucket_name():
    try:
        from django.conf import settings
        bucket = getattr(settings, 'GCS_BUCKET_NAME', None)
        if bucket:
            return bucket
    except Exception:
        pass
    return os.environ.get('GCS_BUCKET_NAME')

GROQ_API_KEY = get_groq_api_key()
GEMINI_API_KEY = get_gemini_api_key()
YOUTUBE_API_KEY = get_youtube_api_key()
GCS_BUCKET_NAME = get_gcs_bucket_name()

try:
    from google.cloud import storage
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False

logger = logging.getLogger('moodtune')

def call_with_retry(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait_time = (2 ** attempt)
            logger.warning(f"Retry {attempt+1}/{max_retries} after {wait_time}s: {e}")
            time.sleep(wait_time)

def fetch_youtube(song, api_key):
    """
    Searches YouTube for a single song, retrieves up to 5 candidates,
    verifies their embeddable status in batch, and returns the first valid video.
    """
    yt_url = "https://www.googleapis.com/youtube/v3/search"
    search_query = song.get("search_query")
    if not search_query:
        search_query = f"{song.get('title')} {song.get('artist')} official audio"

    params = {
        "key": api_key,
        "q": search_query,
        "type": "video",
        "videoCategoryId": "10", # Music category
        "maxResults": 5,
        "part": "snippet",
        "fields": "items(id/videoId,snippet/title,snippet/thumbnails/medium/url,snippet/channelTitle)",
        "videoEmbeddable": "true"
    }

    search_time = 0.0
    embed_time = 0.0

    def make_search_call():
        start_time = time.time()
        api_name = "YouTube search"
        try:
            res = requests.get(yt_url, params=params, timeout=10)
            res.raise_for_status()
            quota_header = res.headers.get('x-quota-remaining') or res.headers.get('X-Quota-Remaining')
            if quota_header:
                logger.warning(f"YouTube API remaining quota: {quota_header}")
            logger.info(f"API_CALL_SUCCESS: {api_name} took {time.time()-start_time:.2f}s")
            return res
        except requests.exceptions.Timeout as e:
            logger.error(f"API_CALL_FAILED: {api_name} error: Network timeout (timeout parameter triggered) took {time.time()-start_time:.2f}s")
            raise
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else "Unknown"
            logger.error(f"API_CALL_FAILED: {api_name} error: HTTP {status_code} - {str(e)} took {time.time()-start_time:.2f}s")
            raise
        except Exception as e:
            logger.error(f"API_CALL_FAILED: {api_name} error: {str(e)} took {time.time()-start_time:.2f}s")
            raise

    search_start = time.time()
    try:
        res = call_with_retry(make_search_call)
        res_data = res.json()
        items = res_data.get("items", [])
    except Exception:
        items = []
    search_time = time.time() - search_start

    # If candidates were found, verify their embeddability using videos endpoint in batch
    valid_video = None
    if items:
        video_ids = [item.get("id", {}).get("videoId", "") for item in items if item.get("id", {}).get("videoId")]
        if video_ids:
            videos_url = "https://www.googleapis.com/youtube/v3/videos"
            v_params = {
                "key": api_key,
                "part": "status,snippet",
                "id": ",".join(video_ids),
                "fields": "items(id,status/embeddable,snippet/title,snippet/thumbnails/medium/url,snippet/channelTitle)"
            }

            def make_embed_call():
                start_time = time.time()
                api_name = "YouTube videos.list embeddable check"
                try:
                    v_res = requests.get(videos_url, params=v_params, timeout=10)
                    v_res.raise_for_status()
                    quota_header = v_res.headers.get('x-quota-remaining') or v_res.headers.get('X-Quota-Remaining')
                    if quota_header:
                        logger.warning(f"YouTube API remaining quota: {quota_header}")
                    logger.info(f"API_CALL_SUCCESS: {api_name} took {time.time()-start_time:.2f}s")
                    return v_res
                except requests.exceptions.Timeout as e:
                    logger.error(f"API_CALL_FAILED: {api_name} error: Network timeout (timeout parameter triggered) took {time.time()-start_time:.2f}s")
                    raise
                except requests.exceptions.HTTPError as e:
                    status_code = e.response.status_code if e.response is not None else "Unknown"
                    logger.error(f"API_CALL_FAILED: {api_name} error: HTTP {status_code} - {str(e)} took {time.time()-start_time:.2f}s")
                    raise
                except Exception as e:
                    logger.error(f"API_CALL_FAILED: {api_name} error: {str(e)} took {time.time()-start_time:.2f}s")
                    raise

            embed_start = time.time()
            try:
                v_res = call_with_retry(make_embed_call)
                v_data = v_res.json()
                v_items = v_data.get("items", [])
                
                # Map video details by video id
                embeddable_map = {}
                details_map = {}
                for v_item in v_items:
                    v_id = v_item.get("id")
                    status = v_item.get("status", {})
                    is_embeddable = status.get("embeddable", False)
                    embeddable_map[v_id] = is_embeddable
                    
                    snippet = v_item.get("snippet", {})
                    details_map[v_id] = {
                        "title": snippet.get("title"),
                        "artist": snippet.get("channelTitle"),
                        "thumbnails": snippet.get("thumbnails", {})
                    }
                
                # Select the first candidate in original search result order that is embeddable
                for item in items:
                    v_id = item.get("id", {}).get("videoId")
                    if v_id and embeddable_map.get(v_id) is True:
                        details = details_map.get(v_id, {})
                        
                        # Extract thumbnail
                        thumbnails = details.get("thumbnails", {})
                        thumbnail = ""
                        for size in ["medium", "high", "default"]:
                            if size in thumbnails:
                                thumbnail = thumbnails[size].get("url", "")
                                break
                                
                        valid_video = {
                            "title": details.get("title") or item.get("snippet", {}).get("title", song.get("title")),
                            "artist": details.get("artist") or item.get("snippet", {}).get("channelTitle", song.get("artist")),
                            "youtube_id": v_id,
                            "thumbnail": thumbnail,
                        }
                        break
            except Exception:
                pass
            embed_time = time.time() - embed_start

    if valid_video:
        valid_video["_search_time"] = search_time
        valid_video["_embed_time"] = embed_time
        return valid_video

    # If no embeddable video found, return fallback/unplayable signature
    return {
        "title": song.get("title", ""),
        "artist": song.get("artist", ""),
        "youtube_id": "",
        "thumbnail": "",
        "unplayable": True,
        "_search_time": search_time,
        "_embed_time": embed_time
    }

def get_mood_playlist(mood_text):
    """
    Analyzes the user's mood using Gemini, generates a list of 8 song recommendations,
    and searches YouTube to verify/fetch embeddable details. If any are unplayable,
    queries Gemini for replacements until exactly 8 playable songs are secured.
    """
    try:
        gemini_key = get_gemini_api_key()
        youtube_key = get_youtube_api_key()

        if not gemini_key:
            raise ValueError("gemini_api environment variable is not set on Render.")
        if not youtube_key:
            raise ValueError("youtube_api environment variable is not set on Render.")

        client = genai.Client(api_key=gemini_key)
        good_songs = []
        unplayable_titles = []
        mood_analysis = "Here is some music to match your vibe"
        playlist_name = "Mood Playlist"

        gemini_total_time = 0.0
        youtube_total_time = 0.0
        embed_check_total_time = 0.0

        for attempt in range(3):
            needed = 8 - len(good_songs)
            if needed <= 0:
                break

            if attempt == 0:
                # Initial prompt for 8 songs
                prompt = f"""You are a music psychologist and DJ. 
A user is feeling: "{mood_text}"

Based on this mood, recommend exactly 8 songs.
Mix Hindi and English songs — real popular songs only.
Think about what their mind NEEDS right now, not just what they asked.

Return ONLY this JSON, nothing else:
{{
  "mood_analysis": "one line describing their emotional state warmly",
  "playlist_name": "creative playlist name (max 5 words)",
  "songs": [
    {{
      "title": "exact song title",
      "artist": "artist name",
      "search_query": "song title artist name official audio"
    }}
  ]
}}"""
            else:
                # Prompt for needed replacements
                avoid_list = [f"'{s['title']}' by '{s['artist']}'" for s in good_songs]
                avoid_str = ", ".join(avoid_list + [f"'{t}'" for t in unplayable_titles])
                prompt = f"""You are a music psychologist and DJ. 
A user is feeling: "{mood_text}"

We need exactly {needed} replacement song recommendation(s) because some earlier recommendations were not embeddable or unavailable.
Do NOT recommend any of these songs which are already in the playlist or were unplayable:
{avoid_str}

Recommend exactly {needed} new replacement songs matching this mood.
Mix Hindi and English songs — real popular songs only.

Return ONLY this JSON, nothing else:
{{
  "songs": [
    {{
      "title": "exact song title",
      "artist": "artist name",
      "search_query": "song title artist name official audio"
    }}
  ]
}}"""

            # Call Gemini API
            gemini_start = time.time()
            api_name = "Gemini playlist generation"
            try:
                def make_gemini_call():
                    return client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                        config={"response_mime_type": "application/json"}
                    )
                
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(make_gemini_call)
                    response = future.result(timeout=10)
                
                logger.info(f"API_CALL_SUCCESS: {api_name} took {time.time()-gemini_start:.2f}s")
            except Exception as e:
                # Check for timeout
                if isinstance(e, TimeoutError):
                    logger.error(f"API_CALL_FAILED: {api_name} error: Network timeout (Gemini call timed out after 10s) took {time.time()-gemini_start:.2f}s")
                elif isinstance(e, errors.APIError):
                    if e.code == 429:
                        logger.error(f"GEMINI_API_RATE_LIMIT (429): {api_name} error: rate limit hit took {time.time()-gemini_start:.2f}s")
                    logger.error(f"API_CALL_FAILED: {api_name} error: APIError {e.code} - {e.message} took {time.time()-gemini_start:.2f}s")
                else:
                    logger.error(f"API_CALL_FAILED: {api_name} error: {str(e)} took {time.time()-gemini_start:.2f}s")
                raise
            finally:
                gemini_total_time += (time.time() - gemini_start)

            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                lines = raw_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw_text = "\n".join(lines).strip()

            data = json.loads(raw_text)

            if attempt == 0:
                mood_analysis = data.get("mood_analysis", mood_analysis)
                playlist_name = data.get("playlist_name", playlist_name)
            
            candidates = data.get("songs", [])
            if not candidates:
                continue

            # Fetch YouTube details for candidate recommendations in parallel
            with ThreadPoolExecutor(max_workers=min(len(candidates), 8)) as executor:
                futures = {executor.submit(fetch_youtube, song, YOUTUBE_API_KEY): song for song in candidates}
                for future in as_completed(futures):
                    song_req = futures[future]
                    try:
                        res_song = future.result()
                        if res_song:
                            youtube_total_time += res_song.get("_search_time", 0.0)
                            embed_check_total_time += res_song.get("_embed_time", 0.0)
                            if not res_song.get("unplayable") and res_song.get("youtube_id"):
                                # Check for duplicates
                                if not any(g['youtube_id'] == res_song['youtube_id'] for g in good_songs):
                                    good_songs.append(res_song)
                                else:
                                    unplayable_titles.append(song_req.get("title", ""))
                            else:
                                unplayable_titles.append(song_req.get("title", ""))
                        else:
                            unplayable_titles.append(song_req.get("title", ""))
                    except Exception:
                        unplayable_titles.append(song_req.get("title", ""))

        # Ensure order/limit of good songs to exactly 8
        final_songs = good_songs[:8]

        return {
            "mood_analysis": mood_analysis,
            "playlist_name": playlist_name,
            "songs": final_songs,
            "gemini_time": gemini_total_time,
            "youtube_time": youtube_total_time,
            "embed_check_time": embed_check_total_time
        }

    except Exception as e:
        logger.error(f"Error in get_mood_playlist: {e}")
        return None

def search_songs(query):
    """
    Searches YouTube for songs matching the query and returns a list of up to 10 results.
    """
    try:
        youtube_key = get_youtube_api_key()
        if not youtube_key:
            raise ValueError("YOUTUBE_API_KEY is not configured.")

        yt_url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "key": youtube_key,
            "q": query,
            "type": "video",
            "videoCategoryId": "10", # Music category
            "maxResults": 10,
            "part": "snippet",
            "fields": "items(id/videoId,snippet/title,snippet/thumbnails/medium/url,snippet/channelTitle)",
            "videoEmbeddable": "true"
        }

        def make_songs_search_call():
            start_time = time.time()
            api_name = "YouTube search"
            try:
                res = requests.get(yt_url, params=params, timeout=10)
                res.raise_for_status()
                quota_header = res.headers.get('x-quota-remaining') or res.headers.get('X-Quota-Remaining')
                if quota_header:
                    logger.warning(f"YouTube API remaining quota: {quota_header}")
                logger.info(f"API_CALL_SUCCESS: {api_name} took {time.time()-start_time:.2f}s")
                return res
            except requests.exceptions.Timeout as e:
                logger.error(f"API_CALL_FAILED: {api_name} error: Network timeout (timeout parameter triggered) took {time.time()-start_time:.2f}s")
                raise
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else "Unknown"
                logger.error(f"API_CALL_FAILED: {api_name} error: HTTP {status_code} - {str(e)} took {time.time()-start_time:.2f}s")
                raise
            except Exception as e:
                logger.error(f"API_CALL_FAILED: {api_name} error: {str(e)} took {time.time()-start_time:.2f}s")
                raise

        res = call_with_retry(make_songs_search_call)
        res_data = res.json()
        items = res_data.get("items", [])

        songs = []
        for item in items:
            video_id = item.get("id", {}).get("videoId", "")
            snippet = item.get("snippet", {})
            title = snippet.get("title", "")
            artist = snippet.get("channelTitle", "")
            
            thumbnails = snippet.get("thumbnails", {})
            thumbnail = ""
            for size in ["medium", "high", "default"]:
                if size in thumbnails:
                    thumbnail = thumbnails[size].get("url", "")
                    break

            songs.append({
                "youtube_id": video_id,
                "title": title,
                "artist": artist,
                "thumbnail": thumbnail
            })

        return songs

    except Exception as e:
        logger.error(f"Error in search_songs: {e}")
        return None

def save_to_cloud(session_id, playlist_data, mood_text):
    """
    Saves the recommended playlist JSON and the mood text to Google Cloud Storage.
    Returns the public URL of the saved playlist JSON file.
    """
    if not GCS_AVAILABLE or not GCS_BUCKET_NAME:
        return None

    try:
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET_NAME)

        # 2. Save playlist data as JSON file
        filename = f"playlists/{session_id}/{playlist_data['playlist_name']}.json"
        blob = bucket.blob(filename)
        blob.upload_from_string(
            json.dumps(playlist_data),
            content_type='application/json'
        )

        # 3. Save mood history as text
        history_filename = f"moods/{session_id}/history.txt"
        history_blob = bucket.blob(history_filename)
        history_blob.upload_from_string(mood_text)

        # 4. Return the public URL of saved file
        return blob.public_url
    except Exception:
        return None

