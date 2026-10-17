# Final real-data test: plan, written before development (17 October 2026)

This plan is committed before any change is developed on PHEME and before the test
set's labels are read. The test is run once, and its result is reported whatever it is.

## Data

- **Development:** PHEME (`all-rnr-annotated-threads`), all 9 crises, with RumourEval
  2019 training and development stance labels. Already used for the first real-data
  run (`../pheme-first-run/`), so it is development data from now on.
- **Test:** the RumourEval 2019 English **Twitter test set**: 56 threads on 28 topics
  from 2017–18, none of them in PHEME. Labels: `final-eval-key.json`, subtask B
  (veracity) and subtask A (stance). Not read until the test run.

## What is tested

- **Unit:** a thread is an event (RumourEval subtask B's unit; test topics are not
  grouped into stories). Its source tweet and replies are the observations.
- **Outcome:** true (happened) vs false. Unverified threads are left out and counted.
- **Stance, primary:** predicted by the development stance model, trained on all
  RumourEval training and development labels. **Secondary:** the test set's gold stance
  (subtask A), as an upper bound.
- **Training:** every method learns only from PHEME's true and false stories
  (reliability, calibration); nothing is fitted on the test set.
- **Checkpoints:** final (primary), and T+1h and T+6h after the source tweet.

## Methods and comparisons

Majority (B3), TruthFinder (B5), B7 (`socialsensing-dep-nosilence` and `-sup`), the
first proposed model (`reliability-dep`), and the revised model chosen on PHEME,
frozen at a commit named in the results before the test run.

- **Primary measure:** Brier score at the final checkpoint.
- **Comparison:** revised model vs each other method, with a paired bootstrap over
  threads (95 % interval, p-value).
- **Also reported:** ECE (adaptive), AUC and accuracy.

## Rules

1. Development (choosing changes, settings, the stance model) uses PHEME only, with
   leave-one-crisis-out evaluation.
2. The test runner is committed before it is run.
3. The test is run once. Every number it gives is reported, including losses to
   baselines. Any later change means a new test set, not a rerun.
