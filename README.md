# MoodTune Deployment on Google Cloud Run

## One-time Setup
```bash
gcloud init
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

## Deploying Updates
```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/moodtune
gcloud run deploy moodtune \
  --image gcr.io/PROJECT_ID/moodtune \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=xxx,YOUTUBE_API_KEY=xxx,GCS_BUCKET_NAME=xxx
```

## Inspect Deployment URL
```bash
gcloud run services describe moodtune --region asia-south1
```
