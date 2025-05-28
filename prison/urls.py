from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('prisoners/', views.prisoner_list, name='prisoner_list'),
    path('prisoners/add/', views.add_prisoner, name='add_prisoner'),
    path('prisoners/<int:prisoner_id>/', views.prisoner_detail, name='prisoner_detail'),
    path('prisoners/<int:prisoner_id>/edit/', views.edit_prisoner, name='edit_prisoner'),
    path('prisoners/<int:prisoner_id>/delete/', views.delete_prisoner, name='delete_prisoner'),
    path('prisoners/<int:prisoner_id>/convicted/', views.add_convicted_details, name='add_convicted_details'),
    path('prisoners/<int:prisoner_id>/remand/', views.add_remand_details, name='add_remand_details'),
    path('prisoners/<int:prisoner_id>/convicted/edit/', views.edit_convicted_details, name='edit_convicted_details'),
    path('prisoners/<int:prisoner_id>/remand/edit/', views.edit_remand_details, name='edit_remand_details'),
    path('prisoners/<int:prisoner_id>/transfer/', views.transfer_prisoner, name='transfer_prisoner'),
    path('prisoners/<int:prisoner_id>/reduce-sentence/', views.apply_sentence_reduction, name='apply_sentence_reduction'),
    path('prisoners/<int:prisoner_id>/report/', views.generate_prisoner_report, name='generate_prisoner_report'),
    path('releases/', views.upcoming_releases_report, name='upcoming_releases_report'),
    path('stations/', views.manage_prison_stations, name='manage_prison_stations'),
    path('stations/<int:station_id>/edit/', views.edit_prison_station, name='edit_prison_station'),
    path('stations/<int:station_id>/delete/', views.delete_prison_station, name='delete_prison_station'),
    path('statistics/api/', views.prison_statistics_api, name='prison_statistics_api'),
    path('releases/', views.upcoming_releases_report, name='upcoming_releases_report'),
    path('stations/create/', views.create_prison_station, name='create_prison_station'),
    path('stations/', views.manage_prison_stations, name='manage_prison_stations'),
    path('stations/<int:station_id>/edit/', views.edit_prison_station, name='edit_prison_station'),
    path('stations/<int:station_id>/delete/', views.delete_prison_station, name='delete_prison_station'),
   
]