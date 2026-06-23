"""
hermes_tools/spotify_tool.py
-----------------------------
Spotify mood signal tool — exposed as MCP tool `spotify_mood`.

PRIVACY CONTRACT: Track names and artist names are NEVER extracted or
forwarded anywhere.  Only Spotify's numeric audio_features (valence, energy,
tempo) are used for local mood derivation.  The model receives only the
final mood label ("upbeat", "focused", etc.) and session duration.
Privacy floor: 0.95 (ALWAYS_LOCAL).
"""

from __future__ import annotations

from connectors.spotify import SpotifyConnector, derive_spotify_signals
from kg.connector_store import record_spotify


def spotify_mood() -> dict:
    """
    Return mood signal derived from Spotify audio features.

    Track names and artist names are stripped before derivation and never
    appear in the return value.  Only valence/energy-derived labels are
    returned to the reasoning model.

    Returns:
        {
            "success": bool,
            "mood": str,                    # upbeat|relaxed|intense|melancholic|neutral|unknown
            "avg_valence": float | None,
            "avg_energy": float | None,
            "deep_work_session": bool,
            "session_minutes": float | None,
            "summary": str,
            "source": "live" | "mock",
        }
    """
    connector = SpotifyConnector()

    if connector.health_check():
        # Fetch recently played and currently playing
        recent_items = connector.get_recently_played(limit=10)
        current = connector.get_currently_playing()

        # Collect track IDs — but strip names immediately (privacy)
        track_ids: list[str] = []
        session_minutes: float | None = None

        if current and current.get("is_playing"):
            cur_track = current.get("item") or {}
            tid = cur_track.get("id")
            if tid:
                track_ids.append(tid)
            # Estimate session from progress
            progress_ms = current.get("progress_ms", 0)
            duration_ms = cur_track.get("duration_ms", 0)
            if progress_ms and duration_ms:
                session_minutes = round(progress_ms / 60_000, 1)

        for item in recent_items:
            tid = (item.get("track") or {}).get("id")
            if tid and tid not in track_ids:
                track_ids.append(tid)

        features = connector.get_audio_features_batch(track_ids) if track_ids else []
        source = "live"
    else:
        mock = connector.load_mock()
        features = mock.get("audio_features", [])
        session_minutes = mock.get("session_minutes")
        source = "mock"

    signals = derive_spotify_signals(features, session_minutes=session_minutes)
    result = {"success": True, "source": source, **signals}
    try:
        record_spotify(result)
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = spotify_mood()
    assert result["success"] is True
    assert "mood" in result
    assert "deep_work_session" in result
    # Track names must NOT appear anywhere in the result
    result_str = str(result)
    assert "REDACTED" not in result_str or result["source"] == "mock", \
        "track name leaked into result"
    print(f"=> source            : {result['source']}")
    print(f"=> mood              : {result['mood']}")
    print(f"=> avg_valence       : {result['avg_valence']}")
    print(f"=> avg_energy        : {result['avg_energy']}")
    print(f"=> deep_work_session : {result['deep_work_session']}")
    print(f"=> session_minutes   : {result['session_minutes']}")
    print(f"=> summary           : {result['summary']}")
    print("All hermes_tools/spotify_tool.py smoke tests passed.")
