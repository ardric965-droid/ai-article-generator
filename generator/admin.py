from django.contrib import admin
from .models import GenerationJob, ArticleResult

# Register your models here.
admin.site.register(GenerationJob)
admin.site.register(ArticleResult)