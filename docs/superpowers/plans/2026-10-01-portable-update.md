# Portable Update Implementation Plan

Goal: make branch-aware Git updates repeatable without active-script corruption.
Architecture: a fully parsed BAT command block starts a stdlib Python worker.
The worker applies the existing network policy, fetches the current branch once,
pins its SHA, calls the existing safe Git helper, then refreshes root launchers.
No main bootstrap is used for this path. Release updating stays separate.

- [x] Add real Git tests in tests/test_portable_update_worker.py for channel,
  repeated update, missing remote, detached HEAD and local conflict preservation.
- [x] Run pytest and verify failing missing worker assertion.
- [x] Add scripts/portable/update_portable.py and explicit target support in
  portable_git.py. Never reset, clean, stash or change global configuration.
- [x] Replace both Git BAT templates with one fully parsed handoff block.
  Preserve exit status; load all commands before replacing the root BAT.
- [x] Disable online bootstrap in Git checkouts; Git owns tracked scripts.
- [ ] Run actual Windows BAT entry tests, packaging tests and network tests.
- [ ] Commit, push #396, record exact verified scope. Do not merge automatically.
- [ ] Use the corrected GPU package from #397 for final combined acceptance.
