# 🎵 MoodTune

[![Django](https://img.shields.io/badge/django-%23092E20.svg?style=for-the-badge&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Gemini AI](https://img.shields.io/badge/Gemini%20AI-8E75C2?style=for-the-badge&logo=googlegemini&logoColor=white)](https://deepmind.google/technologies/gemini/)
[![YouTube API](https://img.shields.io/badge/YouTube%20API-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://developers.google.com/youtube/v3)
[![WebSockets](https://img.shields.io/badge/WebSockets-010101?style=for-the-badge&logo=socket.io&logoColor=white)](https://channels.readthedocs.io/)
[![Railway](https://img.shields.io/badge/Railway-131415?style=for-the-badge&logo=railway&logoColor=white)](https://railway.app/)

MoodTune is an AI-powered, real-time social music player that matches your tracks with your feelings. By combining multimodal facial expression analysis, text prompt mood mapping, and collaborative real-time playback synchronization, MoodTune elevates music discovery and shared listening experiences.

---

## ✨ Features

- **🧠 Smart AI Curation**: Describe your current mood or select emojis, and MoodTune will use the Google Gemini API (`gemini-flash-latest`) to generate a customized playlist matching your vibe.
- **📸 Selfie Mood Detection**: Snap or upload a photo using your webcam. MoodTune analyzes facial expressions in real-time, extracts key emotion vectors (mood, confidence level, fun description, and energy level), and automatically starts playing a matching playlist.
- **⚡ Real-Time Listening Rooms**: Create or join listening rooms powered by WebSockets (Django Channels & Daphne). Play, pause, skip, and reorder songs collaboratively with friends, keeping all participants completely in sync.
- **🎧 Continuous Playback & Robust Fallbacks**: Automatically handles region-restricted or unembeddable YouTube videos by triggering a red-bordered toast notification with a redirect to YouTube Music, auto-skipping to the next track after 4 seconds.
- **📁 Dynamic Playlist Management**: Create custom playlists, search for tracks directly, add/remove songs, and reorder playback queues via drag-and-drop.
- **💾 Optimized DB Caching**: Caches identical mood playlist requests within a 24-hour window to minimize API latency and request usage.

---




## 🛠️ Local Development Setup

Follow these steps to set up MoodTune on your local machine:

### 1. Prerequisites
- **Python**: Version 3.10 or higher.
- **Git**: Installed on your path.

### 2. Clone the Repository
```bash
git clone https://github.com/yourusername/moodtune.git
cd moodtune
```

### 3. Create a Virtual Environment
**On Windows:**
```powershell
python -m venv venv
venv\Scripts\activate
```

**On macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Set Up Environment Variables
Create a `.env` file in the project root directory. Use `.env.example` as a template:
```bash
# Windows
copy .env.example .env

# macOS/Linux
cp .env.example .env
```

Open the newly created `.env` file and populate it with your keys:
```ini
SECRET_KEY=your-django-secret-key-here
GEMINI_API_KEY=your-gemini-api-key-here
YOUTUBE_API_KEY=your-youtube-api-key-here
GCS_BUCKET_NAME=your-gcs-bucket-name-here # (Optional)
DEBUG=True
```

### 6. Apply Database Migrations
Create and configure your local SQLite database:
```bash
python manage.py migrate
```

### 7. Run the Server
Since WebSockets are implemented using Django Channels, the application relies on an ASGI configuration. For local testing, you can use either command:

**Using Django Development Server:**
```bash
python manage.py runserver
```
*(Channels automatically redirects HTTP and WebSocket traffic when `daphne` is in installed apps).*

**Using Daphne directly:**
```bash
daphne moodtune.asgi:application
```

Access the app at [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

---

## 🔑 How to Get API Keys

### 1. Google Gemini API Key
1. Navigate to [Google AI Studio](https://aistudio.google.com/).
2. Log in using your Google account credentials.
3. Click on the **Create API Key** button on the left sidebar.
4. Copy the generated key and assign it to `GEMINI_API_KEY` in your `.env` file.

### 2. YouTube Data API v3 Key
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., "MoodTune").
3. Navigate to **APIs & Services** > **Library**.
4. Search for **YouTube Data API v3** and click **Enable**.
5. Once enabled, go to the **Credentials** tab on the left.
6. Click **+ Create Credentials** at the top and select **API key**.
7. Copy the key and assign it to `YOUTUBE_API_KEY` in your `.env` file.

---

## 🚀 Deployment & Demo

### Live Demo
🔗 **[Launch MoodTune Demo (Railway URL Placeholder)](https://moodtune.up.railway.app)**

### Deployment Notes
The repository contains a `Dockerfile` and is pre-configured for automated builds and deployment on **Railway** or **Google Cloud Run**.

To deploy updates manually to Google Cloud Run:
```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/moodtune
gcloud run deploy moodtune \
  --image gcr.io/PROJECT_ID/moodtune \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=xxx,YOUTUBE_API_KEY=xxx,GCS_BUCKET_NAME=xxx
```

---

## ✍️ Author
- **Monali Agarwal**, JECRC University
