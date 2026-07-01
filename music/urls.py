from django.urls import path
from . import views

urlpatterns = [
    path('', views.index_view, name='index'),
    path('generate/', views.generate_playlist_view, name='generate_playlist'),
    path('detect-mood/', views.detect_mood_view, name='detect_mood'),
    path('search/', views.search_view, name='search'),
    path('playlist/create/', views.create_playlist_view, name='create_playlist'),
    path('playlist/add-song/', views.add_song_view, name='add_song'),
    path('playlist/remove-song/', views.remove_song_view, name='remove_song'),
    path('playlist/delete/', views.delete_playlist_view, name='delete_playlist'),
    path('playlist/<int:playlist_id>/', views.get_playlist_view, name='get_playlist'),
    path('playlist/<int:playlist_id>/update-name/', views.update_name_view, name='update_name'),
    path('playlist/<int:playlist_id>/reorder-songs/', views.reorder_songs_view, name='reorder_songs'),
]
