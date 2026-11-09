from datetime import UTC, datetime

from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from django.utils.crypto import salted_hmac

from muqola.identity.models import RateBucket

# Fenêtres fixes, limites IP ET adresse (partagées par tous les workers).
LIMITS = {
    "community": (3600, 10, 10),
    "invite": (3600, 20, 20),
    "signup": (3600, 10, 3),
    "login": (900, 30, 10),
    "resend": (3600, 10, 3),
    "reset": (3600, 10, 3),
    "token": (900, 60, 60),
}


def allowed(request: HttpRequest, action: str, email: str = "") -> bool:
    seconds, ip_max, email_max = LIMITS[action]
    window = int(timezone.now().timestamp()) // seconds
    subjects = [("ip:" + request.META.get("REMOTE_ADDR", "unknown"), ip_max)]
    if email:
        subjects.append(("email:" + email.strip().lower(), email_max))
    # Toujours IP puis adresse : verrouillage cohérent, et aucune création de
    # nouvelle clé d'adresse après épuisement du budget réseau.
    with transaction.atomic():
        for subject, limit in subjects:
            key = salted_hmac(
                "muqola.rate", f"{action}:{window}:{subject}", algorithm="sha256"
            ).hexdigest()
            RateBucket.objects.get_or_create(
                key=key,
                defaults={
                    "expires_at": datetime.fromtimestamp((window + 1) * seconds, UTC),
                },
            )
            bucket = RateBucket.objects.select_for_update().get(key=key)
            if bucket.count >= limit:
                return False
            bucket.count += 1
            bucket.save(update_fields=["count"])
    return True
