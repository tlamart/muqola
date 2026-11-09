from django.conf import settings
from django.db import models


class OperatorAction(models.Model):
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=40)
    target = models.CharField(max_length=80)
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)


class DeletionRequest(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
