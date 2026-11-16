"""Preserve #25's alias/Commons contract independently of disabled CSV imports."""

from html.parser import HTMLParser

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse

from muqola.catalogue.models import Game, GameAlias, GameIllustration
from muqola.catalogue.services import search
from muqola.catalogue.wikidata_importer import illustration
from muqola.communities import services as communities
from muqola.communities.models import Membership
from muqola.inventory.services import add_to_collection
from tests.helpers import approved_game, member

pytestmark = pytest.mark.django_db


def picture(**changes: str) -> dict[str, str]:
    return {
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Synthetic_game.jpg",
        "image_commons_file": "File:Synthetic game.jpg",
        "image_source_url": "https://commons.wikimedia.org/wiki/File:Synthetic_game.jpg",
        "image_license": "CC BY-SA 4.0",
        "image_license_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "image_artist": "Auteur fictif",
        "image_attribution": "Photographie synthétique",
        "image_review_status": "approved_by_owner",
        **changes,
    }


def illustrated_game(**changes: str) -> Game:
    owner = member("Catalogue")
    game = approved_game(owner, {"title": "Les Pions synthétiques"})
    game.data_source, game.data_license = "Wikidata", "CC0"
    game.save()
    image = illustration(picture(**changes), game)
    image.save()
    return game


@pytest.mark.parametrize(
    "changes",
    [
        {"image_url": "http://commons.wikimedia.org/wiki/Special:FilePath/Synthetic_game.jpg"},
        {
            "image_url": "https://commons.wikimedia.org.evil.test/wiki/Special:FilePath/Synthetic_game.jpg"
        },
        {"image_url": "https://127.0.0.1/private"},
        {"image_url": "javascript:alert(1)"},
        {
            "image_url": "https://user@commons.wikimedia.org/wiki/Special:FilePath/Synthetic_game.jpg"
        },
        {"image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Synthetic_game.jpg?x=1"},
        {"image_source_url": "https://commons.wikimedia.org/wiki/File:Other_file.jpg"},
        {"image_license_url": "https://creativecommons.org/licenses/by/4.0"},
        {"image_artist": "", "image_attribution": ""},
        {"image_review_status": "rejected"},
    ],
)
def test_invalid_or_unapproved_commons_images_remain_unusable(changes: dict[str, str]) -> None:
    game = approved_game(member(), {"title": "Synthétique"})
    with pytest.raises(ValidationError):
        illustration(picture(**changes), game)
    assert not GameIllustration.objects.exists()


def test_fr_english_alias_search_is_unique_private_and_works_for_copies(client: Client) -> None:
    game = illustrated_game()
    GameAlias.objects.create(game=game, title="Fictional Tokens")
    GameAlias.objects.create(game=game, title="Other Fictional Tokens")
    alice, bob = member(), member("Bob")
    assert search(bob, "FICTIONAL TOKENS").get() == game
    assert search(bob, "synthétiques").get() == game
    community = communities.create(alice, "A")
    Membership.objects.create(community=community, user=bob)
    private = add_to_collection(alice, game.pk, "", "Strictement privé", [])
    shared = add_to_collection(alice, game.pk, "", "Visible", [community.pk])
    client.force_login(bob)
    response = client.get(reverse("inventory:index"), {"title": "FICTIONAL TOKENS"})
    assert list(response.context["games"]) == [game]
    assert response.context["games"][0].copy_count == 1
    assert client.get(reverse("inventory:detail", args=[shared.pk])).status_code == 200
    assert client.get(reverse("inventory:detail", args=[private.pk])).status_code == 404
    with pytest.raises(ValidationError, match="existe déjà"):
        add_to_collection(bob, None, "Fictional Tokens", "", [])
    game.hidden = True
    game.save()
    assert not search(bob, "Fictional Tokens").exists()


def test_image_rendering_escapes_credits_and_keeps_license_separate(client: Client) -> None:
    game = illustrated_game(image_artist="<script>alert(1)</script>")
    client.force_login(member())
    response = client.get(reverse("catalogue:detail", args=[game.pk]))
    body = response.content.decode()
    assert "data-commons-image" in body and "CC BY-SA 4.0" in body and "CC0" in body
    assert "&lt;script&gt;" in body and "<script>alert(1)" not in body
    assert 'referrerpolicy="no-referrer"' in body
    assert (
        "img-src 'self' https://commons.wikimedia.org https://upload.wikimedia.org"
        in response["Content-Security-Policy"]
    )
    game.illustration.image_url = "https://evil.test/image.jpg"
    game.illustration.save()
    assert (
        "data-commons-image"
        not in client.get(reverse("catalogue:detail", args=[game.pk])).content.decode()
    )


def test_alias_normalization_and_database_constraints() -> None:
    game = illustrated_game()
    GameAlias.objects.create(game=game, title="Édition de démonstration")
    assert search(member(), "EDITION DE DEMONSTRATION").count() == 1
    with pytest.raises(IntegrityError), transaction.atomic():
        GameAlias.objects.create(game=game, title="EDITION de démonstration")
    with pytest.raises(IntegrityError), transaction.atomic():
        GameIllustration.objects.filter(game=game).update(review_status="rejected")


def test_illustrated_collection_card_does_not_nest_credit_links(client: Client) -> None:
    class CheckLinks(HTMLParser):
        depth = 0

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag == "a":
                assert self.depth == 0
                self.depth += 1

        def handle_endtag(self, tag: str) -> None:
            if tag == "a":
                self.depth -= 1

    game = illustrated_game()
    actor = member()
    add_to_collection(actor, game.pk, "", "Notes", [])
    client.force_login(actor)
    response = client.get(reverse("inventory:mine"))
    parser = CheckLinks()
    parser.feed(response.content.decode())
    assert parser.depth == 0 and "CC BY-SA 4.0" in response.content.decode()


def test_commons_license_canonicalization_and_optional_cc0_author_are_preserved() -> None:
    game = illustrated_game(
        image_license="CC0",
        image_license_url="http://creativecommons.org/publicdomain/zero/1.0/deed.en",
        image_artist="",
        image_attribution="",
    )
    assert game.illustration.displayable
    assert (
        game.illustration.license_url == "https://creativecommons.org/publicdomain/zero/1.0/deed.en"
    )
    assert game.illustration.artist == ""
