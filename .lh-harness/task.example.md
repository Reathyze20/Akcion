# Smoke test: prove the MEA loop works before trusting it with real work

Produce `.lh-harness/REPORT.md` describing the current state of the backend
test suite.

The report must contain:

1. The exact command used to run the suite, and the interpreter it ran under.
2. The pass / fail / error / skipped counts, taken from real output.
3. For every failing or erroring test: its node id and the first line of the
   failure message.
4. One sentence per failure on whether it looks like a broken test or broken
   product code. Say "unclear" when it is unclear — do not guess.

## Acceptance criteria

- `.lh-harness/REPORT.md` exists.
- Re-running the command in point 1 reproduces the counts in point 2 exactly.
- Every failing test in the real output appears in the report. No invented
  entries.

## Out of scope

Change no source file. This run exists to check that the harness reports what
is true, not to fix anything. A round that edits code outside
`.lh-harness/` has failed, even if the tests get greener.
