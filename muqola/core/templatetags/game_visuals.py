"""Décoration de présentation uniquement ; aucune information d'exemplaire."""

from uuid import UUID

from django import template

register = template.Library()


@register.filter
def cover_tone(value: UUID) -> str:
    return ("ocean", "violet", "ochre", "lagoon")[value.int % 4]
