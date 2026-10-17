"""Helpers to build and read signed lobby cookies in tests."""

from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory

from core.services.lobby import LOBBY_COOKIE_SALT


def sign_lobby_cookie(participant_id):
    """Return the cookie value the lobby service sets for a participant id."""
    response = HttpResponse()
    response.set_signed_cookie(
        settings.LOBBY_COOKIE_NAME, participant_id, salt=LOBBY_COOKIE_SALT
    )
    return response.cookies[settings.LOBBY_COOKIE_NAME].value


def unsign_lobby_cookie(value):
    """Return the participant id carried by a signed lobby cookie."""
    request = RequestFactory().get("/")
    request.COOKIES[settings.LOBBY_COOKIE_NAME] = value
    return request.get_signed_cookie(settings.LOBBY_COOKIE_NAME, salt=LOBBY_COOKIE_SALT)
