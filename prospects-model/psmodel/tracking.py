"""Pitch-level events from complete game records (cache/pbp_live).

One parser for MLB and AAA, so a metric computed from these events means the
same thing at both levels -- which parity_tracking.py then proves against
Baseball Savant's published numbers.
"""
import glob
import os

from . import pbp


def iter_events(game):
    """One dict per PITCH: ids, handedness, result code, zone, and batted-ball
    fields when the pitch was put in play (None otherwise)."""
    plays = (((game or {}).get("liveData") or {}).get("plays") or {}).get("allPlays") or []
    for play in plays:
        m = play.get("matchup") or {}
        batter = (m.get("batter") or {}).get("id")
        pitcher = (m.get("pitcher") or {}).get("id")
        side = (m.get("batSide") or {}).get("code")
        hand = (m.get("pitchHand") or {}).get("code")
        for e in play.get("playEvents") or []:
            if not e.get("isPitch"):
                continue
            det = e.get("details") or {}
            pd = e.get("pitchData") or {}
            hd = e.get("hitData") or {}
            co = hd.get("coordinates") or {}
            yield {"batter": batter, "pitcher": pitcher, "bat_side": side, "pitch_hand": hand,
                   "code": det.get("code"), "zone": pd.get("zone"),
                   "ev": hd.get("launchSpeed"), "la": hd.get("launchAngle"),
                   "dist": hd.get("totalDistance"), "traj": hd.get("trajectory"),
                   "hc_x": co.get("coordX"), "hc_y": co.get("coordY")}


def season_games(season, sport_id):
    """Sorted game_pks with a downloaded record for one level-season."""
    folder = os.path.join(pbp.PBP_DIR, str(int(season)), str(int(sport_id)))
    pks = []
    for f in glob.glob(os.path.join(folder, "*.json.gz")):
        stem = os.path.basename(f).split(".")[0]
        if stem.isdigit():
            pks.append(int(stem))
    return sorted(pks)


def season_events(season, sport_id):
    for pk in season_games(season, sport_id):
        yield from iter_events(pbp.load_game(season, sport_id, pk))


def iter_pitches(game):
    """One dict per PITCH with the fields a pitcher's stuff is measured by: pitch
    type, result code, release speed, spin, induced vertical and horizontal break
    (breaks, inches) and the pfx movement coordinates (a parity variant)."""
    plays = (((game or {}).get("liveData") or {}).get("plays") or {}).get("allPlays") or []
    for play in plays:
        pitcher = ((play.get("matchup") or {}).get("pitcher") or {}).get("id")
        for e in play.get("playEvents") or []:
            if not e.get("isPitch"):
                continue
            det = e.get("details") or {}
            pd = e.get("pitchData") or {}
            br = pd.get("breaks") or {}
            co = pd.get("coordinates") or {}
            yield {"pitcher": pitcher, "type": (det.get("type") or {}).get("code"), "code": det.get("code"),
                   "speed": pd.get("startSpeed"), "spin": br.get("spinRate"),
                   "ivb": br.get("breakVerticalInduced"), "hb": br.get("breakHorizontal"),
                   "pfx_x": co.get("pfxX"), "pfx_z": co.get("pfxZ")}


IN_PLAY_CODES = frozenset({"X", "D", "E"})


def iter_pitch_events(game):
    """One dict per PITCH for the pitch-level stuff model (P-E): who threw it and to
    which side, its physical characteristics (speed, spin, IVB, HB, extension, the
    x0/z0 position at 50 ft) and, on the in-play pitch only, the batted ball's EV,
    LA and the play's result (eventType)."""
    plays = (((game or {}).get("liveData") or {}).get("plays") or {}).get("allPlays") or []
    for play in plays:
        m = play.get("matchup") or {}
        pitcher = (m.get("pitcher") or {}).get("id")
        p_hand = (m.get("pitchHand") or {}).get("code")
        b_side = (m.get("batSide") or {}).get("code")
        event = (play.get("result") or {}).get("eventType")
        for e in play.get("playEvents") or []:
            if not e.get("isPitch"):
                continue
            det = e.get("details") or {}
            pd = e.get("pitchData") or {}
            br = pd.get("breaks") or {}
            co = pd.get("coordinates") or {}
            hd = e.get("hitData") or {}
            in_play = det.get("code") in IN_PLAY_CODES
            yield {"pitcher": pitcher, "p_hand": p_hand, "b_side": b_side,
                   "type": (det.get("type") or {}).get("code"), "code": det.get("code"),
                   "speed": pd.get("startSpeed"), "spin": br.get("spinRate"),
                   "ivb": br.get("breakVerticalInduced"), "hb": br.get("breakHorizontal"),
                   "ext": pd.get("extension"), "x0": co.get("x0"), "z0": co.get("z0"),
                   "ev": hd.get("launchSpeed") if in_play else None,
                   "la": hd.get("launchAngle") if in_play else None,
                   "event": event if in_play else None}


def season_pitches(season, sport_id):
    for pk in season_games(season, sport_id):
        yield from iter_pitches(pbp.load_game(season, sport_id, pk))
