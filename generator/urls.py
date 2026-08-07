from django.urls import path

from generator import views

urlpatterns = [
    path('', views.upload_csv, name='upload_csv'),
    path('jobs/<int:job_id>/status/', views.job_status, name='job_status'),
    path('jobs/<int:job_id>/result/', views.download_result, name='download_result'),
]
