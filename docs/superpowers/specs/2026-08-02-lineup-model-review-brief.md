# Design Review Brief — Lineup Model & Trade Realism

**For:** a design/valuation reasoning pass before implementation
**Date:** 2026-08-02
**Repo:** `C:\Users\bkami\Documents\OttoneuAI` — 12-team Ottoneu 4×4 dynasty (R/HR/OBP/SLG · K/HR9/ERA/WHIP), $400 cap, 1,500 IP season cap
**Read first:** `MODEL.md` (whole model + invariants), then
`docs/superpowers/plans/2026-08-02-pa-budget-lineup.md` (the proposal under review)

---

## 1. Why this work exists

The owner's complaint, verbatim:

> "the trade targets page still doesn't work for me. it continues to basically surface
> trade my best players for their best players with a filter for the points i need, which
> isn't super helpful, and the trade finder doesn't feel realistic."

The aspiration is a trade finder whose proposals have an **obvious reason on both sides** —
the kind of offer you'd actually send another owner without embarrassment. When asked to
rank what "realistic" means, the owner chose, in order:

1. **Motivation-realistic** — there's a clear why for both teams (I'm stacked at OF and
   thin at SP; you're the reverse). *Top priority.*
2. **Value-realistic** — they'd plausibly say yes; not lopsided.
3. **Scale-realistic** — mid-tier and complementary pieces, not only blockbusters.

The owner also contributed a trade archetype the model was completely blind to, worth
quoting because it drove much of the design:

> "sometimes a player with a negative surplus value is a good target because you can get a
> loan to cover the rest of year and the team that had the guy was going to cut him at the
> end of the season because his salary was bad… but if he's good now he's a good target for
> a stretch run as a rental"

League rules that make it real: an **in-season cut costs half the salary in dead money**,
while an **end-of-season cut is free**. So the seller strictly prefers trading a bad
contract to cutting it, and the buyer's future liability is genuinely zero.

## 2. Root diagnosis

`simulateTrade` is **fine** — it already re-optimizes both rosters and blends with actuals.
The defect is upstream, in candidate generation ([targets.html:617-673](../../targets.html)):

```
myOffers   = my roster,    sorted by value, .slice(0, 4)
theirChips = their roster, sorted by value, .slice(0, 5)
```

With 36-52 player rosters (median 42), that explores **20 of 1,764 possible 1-for-1s —
1.1% of the space, drawn entirely from the top by value**. A fairness filter then requires
the two sides to match on value. Top-4 against top-5 by value ⇒ star-for-star is the only
reachable outcome. It is structurally incapable of proposing anything else.

**The unifying insight of the whole effort:** the model reasons in *absolute* value, but
trades happen on *contextual* value — worth **to a specific roster**, over a **specific
holding horizon**, given a team's **competitive posture**. Every fix below is an instance
of making value contextual.

## 3. Shipped so far

**Fix 1 — contracts are options, not obligations** (commits `a4d1e15`…`9c0ebab`).
`dynastyCost` charged every holder three years of escalating salary. Cutting is free at
season's end, so a contract is now priced at the best of {rent this season, hold 1, hold 2},
with value and cost always reporting the same horizon. Productive-but-overpaid players
stopped reading as catastrophic; mean surplus recovery **$8.57**, max **$75.90**.

**Fix 2 — marginal-value engine** (`tradefinder.js`, commits `78c28bc`…`65067e2`).
Re-optimizes a roster with one player removed and scores the delta in SGP-denominator
units at $15/point. `tfBlockedness` = absolute Y0 value − value to his own roster.
518 marginals across 12 teams in **95ms**.

**Not yet built:** the archetype generator (logjam↔hole, rental/salary-dump,
buy-now↔sell-future, consolidation), each proposal carrying an explicit reason.

## 4. The blocker this brief is about

Fix 2's verification surfaced a pre-existing bug that **blocks the generator**.
`optimizeHitterLineup` ranks hitters by `pa × (obp + slg)` — volume-dominated — so injured
stars are benched behind healthy mediocrities and dropped from team aggregation entirely:

| Benched | Starting ahead of him | OPS gap |
|---|---|---|
| Aaron Judge (.971 OPS, 97 RoS PA) | Ceddanne Rafaela (.711, 213 PA) | .260 |
| Juan Soto (.952 OPS, 136 PA) | Daulton Varsho (.718, 187 PA) | .234 |

16 such pairings across 3 of 12 teams. The low PA is **injury**, not part-time usage.

Measured on the affected roster, there are **two distinct defects**:

1. **Misranking** — Judge genuinely beats Rafaela for the slot by **0.915 z (~$13.7)**.
   The proxy benches the better player outright.
2. **The either/or assumption** — letting **both** contribute is worth a further
   **+1.694 z (~$25.4)**. A slot absorbs ~194 RoS PA; injured Judge fills only 50% of one,
   Soto 70%. In reality the slot is shared (start Judge when healthy, the other bat covers)
   and the model discards that entirely.

This is not cosmetic: the chosen 12 feed team aggregation, so it perturbs `calcSGPDenoms`
and every Y0 value **today**. And it makes `tradefinder.js` report Soto and Judge as
$0-marginal "blocked assets" — meaning the generator would advise *"trade Juan Soto, he's
blocked."* That is actively harmful, hence the block.

## 5. The proposal under review

Keep the 12 position slots and scarcity ordering. Two changes:

- **Rate-first ranking** (`hitterRateValue`): `(obp + slg) × min(1, pa / PA_FULL_RATE)`.
  Volume is handled by the budget instead of the ranking; the ramp only suppresses tiny
  samples.
- **Slot supplementation**: the primary contributes his **full** projection; if he falls
  short of the slot's PA budget by more than `PA_MIN_SHARE`, a second eligible bat is added
  under a derived key (`OF1_2`) with counting stats scaled to the shortfall, rates unchanged.

Constants: `PA_PER_SLOT = 650` (full-season, prorated → ~196 RoS PA/slot),
`PA_FULL_RATE = 50`, `PA_MIN_SHARE = 30`.

Chosen for **minimal blast radius**: because the primary is never capped, healthy full-time
lineups produce byte-identical results to today, and only injury-thinned slots change.

Three implementation constraints were verified in the existing code and any alternative
design must respect them:
1. `computeTeamStats` reads `p._proj || p.proj`, so partial usage passes as a scaled clone.
2. 6 of 7 callers pass the lineup straight to `computeTeamStats` without inspecting keys;
   `bid.html` iterates `Object.keys`; `test.html` reads `lu['C']`.
3. `test.html` asserts **no duplicate assignments** — a player fills at most one slot.

`OF_GAME_CAP` and `SLOT_CAP` already exist in `shared.js` but are **dead constants
referenced nowhere** — leftovers from exactly this intent.

## 6. Questions for review

1. **Is `PA_PER_SLOT = 650` right, and should it be a constant at all?** It is fit to a
   single observation (194 observed vs 196 predicted). Should the budget be derived from the
   league's own data each run, the way SGP denominators are self-relative?

2. **Should ranking use OPS, or the actual SGP denominators?** `obp + slg` weights the two
   equally, but the denominators say they are not equally valuable, and it ignores HR/R rates
   entirely. A denominator-aware rate ranking could change *who starts*, not merely whether
   slots are shared. Is OPS a good enough proxy, or a repeat of the same class of error?

3. **"Primary uncapped, backup capped" is pragmatic, not principled.** A healthy 220-PA
   player contributes all 220 against a 196 budget; an injured pairing contributes exactly
   196. Is that acceptable, or should the primary be capped for consistency (at the cost of
   trimming every full-timer and a much larger blast radius)?

4. **Does supplementation perversely reward rostering injured stars?** Their slot gains a
   second contributor. Healthy teams appear to still net more PA, but this has not been
   proven.

5. **One backup per slot, or loop until the budget fills?** Currently one, arbitrarily.

6. **Is the 12-fixed-slot abstraction right at all?** The proposal preserves it to limit
   disruption. A pure PA-budget allocation across the whole lineup — closer to how
   `selectPitchers` fills an innings budget — may be the more correct model, and the current
   proposal quietly forecloses it. Position eligibility is the complication.

## 7. Failure mode to hunt for

Earlier today the same author introduced a bug worth using as a calibration example. The
proposal was to prorate the year-0 salary in the contract-horizon math, justified by
invariant #1 ("Y0 projections are RoS; Y1/Y2 are full-season").

**That was wrong.** Invariant #1 governs projection *stat lines*. Y0 *dollar values* are
normalized to the full $4,800 pool regardless of date — verified: rostered Y0 values sum to
exactly $4800 on Aug 2 with `rosProrationFactor` 0.302. Salary and value were already on the
same scale. Prorating inflated every surplus by ~$5.64 and priced Bobby Witt Jr. at $68 as a
**+$16 rental**. Only live-data verification caught it.

**The failure mode: over-applying an invariant to a quantity it does not govern, and
reasoning about scale without checking it.** Worth hunting for the same shape in the
proposal above — particularly in question 1 (is a PA budget even the right unit?) and
question 3 (are capped and uncapped contributions on the same scale?).

## 8. Out of scope

Mechanical implementation, test structure, and the Node verification harness are settled and
do not need review. What is wanted is judgment on the **model**: whether the PA-budget
framing is correct, whether the ranking is right, and whether question 6 should reopen the
slot abstraction before more is built on top of it.

Also deliberately deferred, not for this pass: the +$2/+$4 arbitration escalation
(MODEL.md §4 notes it understates star keeper costs) — changing it alongside these makes
drift unattributable.
