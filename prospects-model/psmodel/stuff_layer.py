"""The pitcher stuff layer (P-D): P-C's season-level stuff score, refit as-of a
vantage, for AAA pitchers -- the pitcher counterpart of tracking_layer's step-1
helpers. The layer math (residualize / trust_weight / adjust) is tracking_layer's."""
from . import evaluate, step1, stuff


def mapping_table(mlb_table, v):
    """MLB metric rows whose outcome season (t + 1) is known by v."""
    return {k: m for k, m in mlb_table.items() if k[1] <= v - 1}


def stuff_model(v, mlb_table, values, mlb_stats, keys, kind):
    rows = step1.complete(stuff.mlb_rows(mapping_table(mlb_table, v), values, mlb_stats, threshold=0.0), keys)
    return evaluate.fit(rows, keys, kind)


def offsets(v, aaa_table, mlb_table, metrics):
    """AAA->MLB offsets from same-season pairs in seasons <= v."""
    return stuff.fit_translation({k: m for k, m in aaa_table.items() if k[1] <= v},
                                 {k: m for k, m in mlb_table.items() if k[1] <= v}, metrics)


def aaa_scores(aaa_table, aaa_stats, model, translation, keys, seasons_wanted):
    """{(player_id, season): stuff score} for AAA pitcher-seasons with >= MIN_PITCHES
    tracked pitches, a StatsAPI row and every key present after translation."""
    out = {}
    for (pid, s), m in aaa_table.items():
        st = aaa_stats.get((pid, s))
        if s not in seasons_wanted or st is None or (m.get("pitches") or 0) < stuff.MIN_PITCHES:
            continue
        f = step1.translate(stuff._features(m, st), translation)
        if all(f.get(k) is not None for k in keys):
            out[(pid, s)] = float(evaluate.predict(model, [{"f": f}], keys)[0])
    return out
