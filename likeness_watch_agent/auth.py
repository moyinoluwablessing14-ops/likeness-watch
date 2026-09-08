"""
Verifies Google Sign-In ID tokens server-side. Never trust an ID token just
because the browser sent it — verifying against Google's public keys is what
actually proves who the person is.
"""

import os
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")

_request = google_requests.Request()


def verify_google_token(token: str) -> dict | None:
    """Returns {'uid', 'email', 'name'} if the token is valid, else None."""
    if not GOOGLE_OAUTH_CLIENT_ID:
        return None
    try:
        payload = id_token.verify_oauth2_token(token, _request, GOOGLE_OAUTH_CLIENT_ID)
        return {"uid": payload["sub"], "email": payload.get("email"), "name": payload.get("name", "")}
    except Exception:
        return None
