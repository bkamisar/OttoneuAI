"""Pairwise interaction strength: Friedman's H, unnormalized.

For features j and k, the part of their joint partial dependence that is NOT the
sum of their separate effects. Unnormalized (in target units, SGP) so pairs rank by
how much value the interaction moves; the normalized H ranks tiny effects as
highly as large ones.
"""
import numpy as np


def _pd(model, X, cols):
    """Partial dependence at each row's values of `cols`, averaged over X as the
    background: one predict call on len(X) ** 2 rows."""
    n = len(X)
    big = np.tile(X, (n, 1))
    for c in cols:
        big[:, c] = np.repeat(X[:, c], n)
    p = model.predict(big).reshape(n, n).mean(axis=1)
    return p - p.mean()


def h_stat(model, X, j, k, cache=None):
    cache = {} if cache is None else cache
    for c in (j, k):
        if c not in cache:
            cache[c] = _pd(model, X, [c])
    resid = _pd(model, X, [j, k]) - cache[j] - cache[k]
    return float(np.sqrt(np.mean(resid ** 2)))


def top_pairs(model, X, keys, n=10):
    """[(strength, key_j, key_k)] strongest first."""
    cache = {}
    scores = [(h_stat(model, X, j, k, cache), keys[j], keys[k])
              for j in range(len(keys)) for k in range(j + 1, len(keys))]
    return sorted(scores, key=lambda t: -t[0])[:n]
