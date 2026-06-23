"""
connectors/spotify.py
---------------------
Spotify Web API connector.

Auth: OAuth 2.0 PKCE flow.  Tokens are stored in AppConfig
(spotify_access_token / spotify_refresh_token).

Privacy contract: track names and artist names are NEVER forwarded to any
model (local or cloud).  Only numeric audio features (valence, energy, tempo)
from Spotify's own audio_features endpoint are used, and only the final
derived mood label ("upbeat", "focused", etc.) is passed to the Hermes
reasoning layer.  Privacy floor: 0.95.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Optional

import requests

from config.store import get_config, update_config

_BASE        = "https://api.spotify.com/v1"
_TOKEN_URL   = "https://accounts.spotify.com/api/token"
_TIMEOUT     = 10
_RECENT_LIMIT = 10   # tracks for rolling mood window

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

def _refresh_spotify_token() -> Optional[str]:
    """Exchange the stored refresh token for a new access token. Never raises."""
    cfg = get_config()
    if not (cfg.spotify_client_id and cfg.spotify_client_secret and cfg.spotify_refresh_token):
        return None
    try:
        credentials = base64.b64encode(
            f"{cfg.spotify_client_id}:{cfg.spotify_client_secret}".encode()
        ).decode()
        resp = requests.post(
            _TOKEN_URL,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "refresh_token", "refresh_token": cfg.spotify_refresh_token},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        update_config(
            spotify_access_token=data["access_token"],
            spotify_refresh_token=data.get("refresh_token", cfg.spotify_refresh_token),
        )
        return data["access_token"]
    except Exception as exc:  # noqa: BLE001
        print(f"[Spotify] WARNING: token refresh failed ({exc}).")
        return None


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------

class SpotifyConnector:
    """Reads Spotify playback data and derives mood signals locally."""

    source_name = "spotify"

    def __init__(self) -> None:
        self._cfg = get_config()

    def _headers(self, token: Optional[str] = None) -> dict[str, str]:
        tok = token or self._cfg.spotify_access_token
        return {"Authorization": f"Bearer {tok}"}

    def _get(self, path: str, params: Optional[dict] = None) -> Optional[requests.Response]:
        """GET with one automatic token-refresh retry on 401."""
        try:
            resp = requests.get(
                f"{_BASE}{path}",
                headers=self._headers(),
                params=params,
                timeout=_TIMEOUT,
            )
            if resp.status_code == 401:
                new_token = _refresh_spotify_token()
                if not new_token:
                    return None
                resp = requests.get(
                    f"{_BASE}{path}",
                    headers=self._headers(new_token),
                    params=params,
                    timeout=_TIMEOUT,
                )
            return resp
        except Exception as exc:  # noqa: BLE001
            print(f"[Spotify] ERROR: GET {path} failed ({exc}).")
            return None

    # -- health -------------------------------------------------------------

    def health_check(self) -> bool:
        """True when an access token is present and the API is reachable."""
        if not self._cfg.spotify_access_token:
            return False
        resp = self._get("/me")
        return resp is not None and resp.status_code == 200

    # -- data fetchers (return raw dicts — never logged or sent to cloud) ---

    def get_currently_playing(self) -> Optional[dict]:
        """Return the currently playing item dict, or None if nothing is playing."""
        resp = self._get("/me/player/currently-playing")
        if resp is None or resp.status_code == 204 or not resp.content:
            return None
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return None

    def get_recently_played(self, limit: int = _RECENT_LIMIT) -> list[dict]:
        """Return the N most recently played track items (newest first)."""
        resp = self._get("/me/player/recently-played", params={"limit": limit})
        if resp is None or resp.status_code != 200:
            return []
        try:
            return resp.json().get("items", [])
        except Exception:  # noqa: BLE001
            return []

    def get_audio_features(self, track_id: str) -> Optional[dict]:
        """
        Return audio features for a single track.
        Called by derive_spotify_signals — result stays local.
        """
        resp = self._get(f"/audio-features/{track_id}")
        if resp is None or resp.status_code != 200:
            return None
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return None

    def get_audio_features_batch(self, track_ids: list[str]) -> list[dict]:
        """Return audio features for up to 100 track IDs in one call."""
        if not track_ids:
            return []
        resp = self._get(
            "/audio-features",
            params={"ids": ",".join(track_ids[:100])},
        )
        if resp is None or resp.status_code != 200:
            return []
        try:
            return [f for f in resp.json().get("audio_features", []) if f]
        except Exception:  # noqa: BLE001
            return []

    # -- mock fallback ------------------------------------------------------

    def load_mock(self) -> dict:
        """Return mock Spotify data from data/mock_spotify.json."""
        path = DATA_DIR / "mock_spotify.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}


# ---------------------------------------------------------------------------
# Mood derivation (pure — local only, no track names)
# ---------------------------------------------------------------------------

def _mood_label(valence: float, energy: float) -> str:
    """
    Derive a mood label from Spotify's valence [0–1] and energy [0–1].
    Only these two numeric values are used — track names never appear here.
    """
    if valence > 0.6 and energy > 0.6:
        return "upbeat"
    if valence > 0.6 and energy < 0.4:
        return "relaxed"
    if valence < 0.4 and energy > 0.6:
        return "intense"
    if valence < 0.4 and energy < 0.4:
        return "melancholic"
    return "neutral"


def _is_deep_work(energy: float, valence: float) -> bool:
    """Focused work session: moderate energy, moderate valence."""
    return 0.3 <= energy <= 0.6 and 0.4 <= valence <= 0.7


def derive_spotify_signals(
    features_list: list[dict],
    session_minutes: Optional[float] = None,
) -> dict:
    """
    Compute mood signals from a list of audio_features dicts.
    Track names and artists are NOT passed here — callers extract
    only the numeric feature dicts before calling this function.

    Args:
        features_list: list of Spotify audio_features dicts (valence, energy, …)
        session_minutes: total continuous playback duration if known
    """
    if not features_list:
        return {
            "mood": "unknown",
            "avg_valence": None,
            "avg_energy": None,
            "deep_work_session": False,
            "session_minutes": session_minutes,
            "summary": "No Spotify playback data available.",
        }

    avg_valence = sum(f.get("valence", 0.5) for f in features_list) / len(features_list)
    avg_energy  = sum(f.get("energy", 0.5)  for f in features_list) / len(features_list)

    mood = _mood_label(avg_valence, avg_energy)
    deep_work = _is_deep_work(avg_energy, avg_valence)

    parts = [f"Mood: {mood} (valence={avg_valence:.2f}, energy={avg_energy:.2f})."]
    if session_minutes is not None:
        parts.append(f"Session: {session_minutes:.0f} min.")
    if deep_work and (session_minutes or 0) > 60:
        parts.append("Looks like a deep-work session.")

    return {
        "mood": mood,
        "avg_valence": round(avg_valence, 3),
        "avg_energy": round(avg_energy, 3),
        "deep_work_session": deep_work and (session_minutes or 0) > 60,
        "session_minutes": session_minutes,
        "summary": " ".join(parts),
    }


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    connector = SpotifyConnector()

    if connector.health_check():
        print("[Spotify] live token found — fetching real data")
        recent = connector.get_recently_played(limit=5)
        track_ids = [
            item["track"]["id"]
            for item in recent
            if item.get("track", {}).get("id")
        ]
        features = connector.get_audio_features_batch(track_ids) if track_ids else []
    else:
        print("[Spotify] no token — using mock data")
        mock = connector.load_mock()
        features = mock.get("audio_features", [])

    signals = derive_spotify_signals(features, session_minutes=75)
    print(f"=> mood              : {signals['mood']}")
    print(f"=> avg_valence       : {signals['avg_valence']}")
    print(f"=> avg_energy        : {signals['avg_energy']}")
    print(f"=> deep_work_session : {signals['deep_work_session']}")
    print(f"=> summary           : {signals['summary']}")

    # Mood label coverage
    assert _mood_label(0.8, 0.8) == "upbeat"
    assert _mood_label(0.8, 0.2) == "relaxed"
    assert _mood_label(0.2, 0.8) == "intense"
    assert _mood_label(0.2, 0.2) == "melancholic"
    assert _mood_label(0.5, 0.5) == "neutral"
    print("=> mood label coverage ok")
    print("All connectors/spotify.py smoke tests passed.")
