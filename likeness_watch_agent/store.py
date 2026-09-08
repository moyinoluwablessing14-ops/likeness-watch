"""
Firestore-backed watchlist storage.

Data model:
  users/{uid}                        -> {email, name}
  users/{uid}/watchlist/{doc_id}      -> {
      talent_name, known_endorsements,
      last_risk_flag, last_finding_urls (list of str),
      created_at
  }

Using a Firestore collection GROUP query, the recheck cron can iterate every
watched talent across every user in one pass without needing to know user IDs
up front.
"""

from google.cloud import firestore

_db = None


def _get_db():
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


def upsert_user(uid: str, email: str, name: str) -> None:
    _get_db().collection("users").document(uid).set({"email": email, "name": name}, merge=True)


def add_to_watchlist(uid: str, talent_name: str, known_endorsements: list[str]) -> str:
    doc_ref = _get_db().collection("users").document(uid).collection("watchlist").document()
    doc_ref.set({
        "talent_name": talent_name,
        "known_endorsements": known_endorsements,
        "last_risk_flag": None,
        "last_finding_urls": [],
        "created_at": firestore.SERVER_TIMESTAMP,
    })
    return doc_ref.id


def remove_from_watchlist(uid: str, doc_id: str) -> None:
    _get_db().collection("users").document(uid).collection("watchlist").document(doc_id).delete()


def list_watchlist(uid: str) -> list[dict]:
    docs = _get_db().collection("users").document(uid).collection("watchlist").stream()
    return [{"id": d.id, **d.to_dict()} for d in docs]


def iter_all_watchlist_entries():
    """Yields (uid, doc_id, watchlist_data) for every watched talent, across
    every user — used by the recheck cron job."""
    for doc in _get_db().collection_group("watchlist").stream():
        uid = doc.reference.parent.parent.id
        yield uid, doc.id, doc.to_dict()


def update_watchlist_state(uid: str, doc_id: str, risk_flag: str, finding_urls: list[str]) -> None:
    _get_db().collection("users").document(uid).collection("watchlist").document(doc_id).update({
        "last_risk_flag": risk_flag,
        "last_finding_urls": finding_urls,
    })


def get_user_email(uid: str) -> str | None:
    doc = _get_db().collection("users").document(uid).get()
    if doc.exists:
        return doc.to_dict().get("email")
    return None
