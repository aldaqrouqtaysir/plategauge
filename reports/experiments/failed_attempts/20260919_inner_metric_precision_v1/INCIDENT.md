# Rejected inner attempt: metric precision domain

- Date: 2026-09-19 (Asia/Dubai)
- Stage/task: first inner-primary attempt, outer fold 0, validation fold 1,
  configuration M1
- Accepted task artifacts: none
- Outer tasks opened: none
- Observed result values: none; only the validator error was surfaced

The runner completed a fit, then rejected the attempt before moving any output
into the immutable `tasks/` directory. The emitted prediction CSV retained the
manifest target at full precision, while the workload payload reused the
training loop's score calculated from float32 batch targets. The semantic
validator recomputed the metric from the CSV/manifest domain and correctly
rejected their tiny numerical mismatch.

Decision D017 keeps the strict validator and changes the published inner metric
to be recomputed from the exact manifest targets and serialized best-checkpoint
predictions. The original `run.json` is retained here as provenance. Temporary
checkpoint/prediction files were cleaned automatically by the fail-closed
runner and never became accepted evidence.
