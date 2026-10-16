# 5 · Integrity: can this field report be trusted?

**Role:** engineered · **Spec:** §6, §11 · **Status:** checks, account score and a simulated evaluation done; real-data evaluation waits for field pilots

The secure-field-system area has two halves:

- **Backend:** authentication, roles, revocation, append-only audit log, and the per-report integrity flags (`backend/app/services/integrity.py`).
- **This module, the AI half:** spots field reports and accounts that *look* wrong even when the login is valid. A compromised account or a careless report still passes authentication.

Flags and scores never block anything. They mark a report or an account for a person to look at, with a reason they can read.

## In → out

| In | Out |
|---|---|
| A field report, earlier reports, public posts | Flags: the backend's six (`observed_in_future`, `old_observation`, `poor_location_accuracy`, `impossible_travel`, `submission_burst`, `photo_reused`) plus two new ones, `location_text_mismatch` and `copied_text` |
| An account's reports and their flags | A risk score from 0 to 1 with readable reasons (account-level only: CARCUX's own field workers, never the public) |

## Pieces

- `checks.py`: every check on one report.
  - `location_text_mismatch`: the text names a locality, upazila or district (found with the extraction module's place finder), and the GPS is farther from every named place than that place's own size, the GPS accuracy and 5 km together.
  - `copied_text`: the text shares at least 80% of its 4-character pieces with a public post, or at least 90% with another account's report of 80+ characters. Texts under 40 characters are not compared.
- `account.py`: compares the account's last 24 hours with its own earlier weeks: how far from its usual area, how many more reports than usual (Poisson tail), how many at hours it almost never reports, and what share carries flags. The parts combine as independent warnings. Under 10 earlier reports, only flags count.
- `simulate.py`: **simulated** workers. 60 accounts over two weeks, with honest noise on the last day (trips to a neighbouring area, weak GPS); 18 of them are misused on the last day, three each of six scenarios: `stolen_far`, `burst`, `copier`, `spoofed_place`, `old_photos`, `night_shift`. Every account and report is made up; none of this is evidence about real people.
- `evaluate.py`: flag precision, per-scenario recall, and the account score's AUC.

```bash
pip install -e ../extraction -e ".[dev]"
python -m carcux_integrity.evaluate                       # seeds 0-2
python -m carcux_integrity.evaluate --first-seed 3 --seeds 5
pytest
```

## Results (simulated data only)

Seeds 0–2 were used while building the rules; seeds 3–7 were run once at the end, with nothing changed afterwards.

**First run, seeds 0–2, before any change.** `copied_text` compared every text with every other account's report at 80%. Its precision was 0.293 (70 ordinary reports flagged). Ordinary workers at the same place write alike ("Mirpur 10 e hatu pani"), which is corroboration, not copying. The rule was narrowed to the version above. In this run, the share of ordinary reports flagged fell from 0.167 to 0.060, and the account score's AUC rose from 0.916 to 0.980.

**Fresh run, seeds 3–7** (90 misused and 210 ordinary accounts):

| Flag (last day) | Precision | Misuse / ordinary |
|---|---|---|
| `copied_text` | 0.681 | 32 / 15 |
| `impossible_travel` | 0.845 | 82 / 15 |
| `location_text_mismatch` | 0.789 | 30 / 8 |
| `photo_reused` | 1.000 | 30 / 0 |
| `submission_burst` | 1.000 | 30 / 0 |
| `poor_location_accuracy` | 0.000 | 0 / 23 |

Ordinary reports with any flag: 5.9%.

| Scenario | Misuse reports with a flag | Accounts marked for review (score ≥ 0.5) |
|---|---|---|
| `stolen_far` | 0.289 | 1.000 |
| `burst` | 0.478 | 0.867 |
| `copier` | 1.000 | 1.000 |
| `spoofed_place` | 1.000 | 0.933 |
| `old_photos` | 1.000 | 1.000 |
| `night_shift` | 0.000 | 0.733 |

Account score: AUC 0.967. At 0.5 or above, precision is 0.814 and recall 0.922.

### What this says, and what it does not

- **Fresh worlds were harder than the development worlds.** `copied_text` precision fell from 0.833 to 0.681. All 15 ordinary hits on seeds 3–7 matched a *public post* written from the same template about the same place. A real public post saying what a worker saw is also corroboration, so this rule needs checking on real reports before it is trusted. It was not changed after the fresh run.
- **Report flags and the account score do different jobs.** A stolen account's first far report trips `impossible_travel`, but the next ones are consistent with each other, so few of them are flagged. Night-time reports break no rule at all. The account score, which compares with the account's own history, catches both.
- **`poor_location_accuracy` is a data-quality flag, not a misuse signal.** It is shown so analysts know a position is rough; its precision against misuse is 0 by design.
- **These are simulated scenarios with rules written by the same person who wrote the simulator.** High numbers show the rules do what they were designed for, not that they would catch a real attacker. The real test is field pilots with labelled incidents.

## Not yet

- Signature and hash verification of submitted reports, with the offline queue (backend).
- Real-data evaluation once field pilots produce reports.
