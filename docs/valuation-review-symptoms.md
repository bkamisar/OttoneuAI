# Valuation reassessment — symptoms (2026-06-10)

User-reported "smells funny" cases, RoS/current-year values:

1. **Juan Soto $117** — one of the best players in baseball, value feels unlikely.
   Yordan Alvarez has the same value. Suspicion: premier hitting is valued too high
   (distribution too top-heavy?).
2. **Many hitters at $0** — e.g. Liam Hicks, Michael Busch. Questions whether the
   replacement-level approach for hitters is fair / too aggressive.
3. **Samuel Basallo $0** — clearly wrong on the low end; one of the best hitters in
   baseball.
4. **Zero-valued pitchers** — Seth Lugo, Joey Cantillo at $0; feels unlikely.

## Context for the review
- Recent ad-hoc patches this session that should be re-examined holistically:
  - Pitcher replacement: sort by ERA ascending, take index REPL_DEPTH.P=156
  - Hitter replacement: sort by raw OBP+SLG (rate only, no PA weighting), take index REPL_DEPTH[pos]
  - Hitters added to ALL eligible position buckets for replacement pools
  - IP_MIN changed 1250 → 400 (RoS projections have partial-season IP)
  - Type-aware name matching (projByNameH / projByNameP)
- Last known-good diagnostics: hitShare 65.2%, hitRate $26.86/SGP,
  replP ERA 4.17 / WHIP 1.304 / SO 79, replOF HR 8 / OBP .319

## Initial hypotheses to check (not yet verified)
- Values may be floored at 0 for anyone below replacement in net SGP, while the
  full $4800 pool is distributed across positive-SGP players only → extreme
  top-heaviness (stars absorb dollars shed by the zeroed-out middle class).
- Replacement comparison may not be volume-consistent: replacement player's raw
  counting stats (over THEIR PA/IP) are subtracted from each player's counting
  stats — a part-time or low-RoS-PA player (Basallo, recent call-up?) can look
  below replacement purely on playing-time volume even with elite rates.
- Pitchers slightly above replacement ERA (Lugo 4.48 vs repl 4.17) may net to ~0
  because rate categories dominate and counting contributions are undervalued.
- Check how $/SGP rate interacts with the count of players sharing the pool.
