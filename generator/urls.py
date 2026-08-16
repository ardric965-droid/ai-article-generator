from django.urls import path

from generator import views

urlpatterns = [
    path('', views.upload_spreadsheet, name='upload_spreadsheet'),
    path('api/generation/preview/', views.preview_generation, name='preview_generation'),
    path('api/generation/create/', views.create_generation_job, name='create_generation_job'),
    path('jobs/<int:job_id>/status/', views.job_status, name='job_status'),
    path('jobs/<int:job_id>/status/api/', views.job_status_api, name='job_status_api'),
    path('jobs/<int:job_id>/stop/', views.stop_job, name='stop_job'),
    path('jobs/<int:job_id>/resume/', views.resume_job, name='resume_job'),
    path('signup/', views.signup, name='signup'),
]
