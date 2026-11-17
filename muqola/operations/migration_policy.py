# ruff: noqa: E501 -- reviewed identifiers and immutable hashes
"""Reviewed historical migrations only; future migrations require a reviewed policy update.

Initial databases are bootstrapped separately; no force flag expands this list.
"""

REVIEWED: dict[str, str] = {
    "catalogue/0001_initial": "e8e3978b47ab717e1af0605358bc7d5d2d5815c72acc726aac465e822afe0bb2",
    "catalogue/0002_wikidata_catalogue": "e90925a7b42a340ad3eba53f694a001941cbef4ac6bd15e3447fd6d017a50949",
    "catalogue/0003_gamedecision_gameexternalidentifier_gamemerge_and_more": "d58defe8dbc56c0a64a32fe5cf815f55bb22bf14e6523cd82906db807ed86710",
    "catalogue/0004_game_game_title_trgm_gamealias_alias_title_trgm": "c0bdc8fd54e3e5059ca9c83ffb49a7d5535f1ef4827ad95a5f6a614e5592ffe2",
    "communities/0001_initial": "5193a187cfee49ce7f8158ca59c4f88d47268e612de18ccdbdd3fcc3b7a5fbb6",
    "communities/0002_invitationevent_and_more": "251ab7bb64ea1a067035dd6c4af70c5957f5046b6fdb5dcf44877f7a3340f59f",
    "identity/0001_initial": "d685dda1c9b4dac7d20dac9bb92f20eb74ac5821e8556ddf9b44de28a16a8a73",
    "identity/0002_accounttoken_ratebucket_alter_user_options_and_more": "abcb04d52c89422989aff163b2712d9d07669ba21a77b5cfb37ff270d1a40d30",
    "identity/0003_user_adult_confirmed_at": "b3f454fbd33fdcf4019cc1d843b326f480e58f10c8946339c18b735bbfe7dd73",
    "inventory/0001_initial": "af962c74e1dc981d6df7f9de4a1dc3d73d1181040ad9492f30f1aa474dc271ed",
    "loans/0001_initial": "1ca9ca101b2db238f1aa7c72645d47f1ca408354daf2d0ec215999c262464536",
    "loans/0002_loanevent_notifications_queued": "9aead5352bae6d1d45ed86569cea7663be9fe8900f08cacf7fb299943a9557b6",
    "notifications/0001_initial": "c64af9255596637c86c50d12b0c760960a130cb1f7b543c19903eeceb36242c9",
    "notifications/0002_remove_emailoutbox_outbox_status_valid_and_more": "cd13767bda9e0e4783467e52256b7068414a65894179d7204a09e6c909712d24",
    "operations/0001_initial": "178a8293d7e349dd5b1cc0a5c8d76d2b1408f167e6ca0d25e5b6c7a1cecc6ac1",
}
