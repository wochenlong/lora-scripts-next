# Portable updater channel and execution safety

Status: implemented; package-level combined acceptance pending.
Target: dev. Follow-up to PR #362. No main changes or release publication.

## Evidence

The local historical Fast artifact was extracted into an isolated directory.
Its application was placed at dev 997e7a9b while retaining its packaged runtime,
then updated toward c48bbbc5 through the root BAT.

- Online bootstrap downloaded main scripts for a dev update. Two downloaded
  files differed from the target commit, so safe fast-forward stopped.
- Skipping bootstrap after restoring those bootstrap-only changes allowed the
  Git fast-forward. This was a diagnostic comparison, not normal-user acceptance.
- Repeating normal update at c48bbbc5 removed dev network-policy code from two
  tracked files. The command returned zero despite BAT command errors.
- Eight explicit user-data/runtime hashes remained unchanged; no stash created.
- BAT self-replacement is the leading explanation for the command errors and
  needs a focused reproducer before claiming that root cause is confirmed.

## Decision

Use a fully parsed BAT handoff block and a separate stdlib updater worker.
Git owns tracked updater scripts: Git checkouts skip online bootstrap entirely.
Load the local safe Git helper before updating, fetch the current local branch,
and pass the captured commit SHA to the helper. Refresh generated root launchers
only after successful fast-forward. No updater is downloaded from main.

Keeping unconditional main bootstrap is rejected because dev and main differ.
Merely switching raw download URLs to a moving dev branch is insufficient:
downloads and the subsequent merge could still refer to different commits.

## Boundaries

- Retain the existing repository identity, network policy and safe Git helper.
- Preserve fast-forward-only behavior, ignored/untracked collision protection,
  and user edits. No automatic stash, hard reset or clean.
- Detached or ambiguous channel selection must stop with a clear error, not
  silently fall back to main.
- Git changes tracked scripts only through the guarded fast-forward.
- Parse the entire BAT handoff before starting the worker, so refreshing its
  file cannot change commands still awaiting execution.
- Use the captured fetched commit even if the remote branch subsequently advances.
- Do not execute staged repository Python with a sys.path rooted only in staging.
  Explicitly retain the application root and use the package interpreter.
- Report worker failure to the user and to the caller; never print success
  solely because a final pause or refresh command succeeded.
- Release-archive updates retain existing semantics; ensure shared bootstrap
  changes do not regress their entrypoint.

## Acceptance

- Real root BAT bootstrap: pre-362 dev to merged dev, then repeat at current HEAD.
- Equivalent main-channel scenario without changing main remotely.
- Branch advances after fetch: original pinned commit is used.
- Partial download, unavailable network, detached HEAD and conflicting local
  files stop safely and preserve original scripts/data.
- Child worker preserves process-only proxy policy.
- No spurious command errors, newly dirty tracked updater files, automatic
  stash entries, or unexplained success exit codes.
- Verify hashes of synthetic datasets, captions, models, outputs, configuration
  and selected runtime files before and after each scenario.
- Windows end-to-end BAT/PowerShell tests and existing Windows/Linux Git tests.

## Isolation and readiness

Work only in this independent clone and disposable fixtures. Do not change the
main development checkout, its processes, Git configuration or GPU workload.
No subagents are used in this side conversation.

This draft is not merge-ready. Implementation, regression tests and a real
package update rerun must precede conversion to a ready PR.

Legacy packages missing the local worker need a complete-package upgrade.
Fail closed instead of silently installing another branch's updater.
