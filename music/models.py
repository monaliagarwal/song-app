from django.db import models

class Playlist(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    session_id = models.CharField(max_length=255)
    mood = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.name

class Song(models.Model):
    playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE, related_name='songs')
    title = models.CharField(max_length=255)
    artist = models.CharField(max_length=255)
    youtube_id = models.CharField(max_length=100)
    thumbnail = models.URLField(max_length=500)
    duration = models.CharField(max_length=50)
    added_at = models.DateTimeField(auto_now_add=True)
    order = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.title} - {self.artist}"

class MoodHistory(models.Model):
    session_id = models.CharField(max_length=255)
    mood_text = models.TextField()
    playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE, related_name='mood_histories')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Mood: {self.mood_text[:30]} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"
