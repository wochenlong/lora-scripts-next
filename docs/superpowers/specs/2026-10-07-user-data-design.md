# Unified User Data

Status: approved; implementation in progress under issue #405.
Target: dev only. Desired delivery date: 2026-10-07, subject to verification.

## Approved Product Direction

Use a project-root user_data directory as the durable source of user configuration.
Browser storage is not authoritative. Changing browser or GUI port must not lose
settings, user presets, or new task records. This is a single-user server profile;
all authorized clients of the same server share it.

Structure:

```text
user_data/
  settings.json
  auth.json
  presets/
  tasks/
    <engine>/
      <YYYY-MM-DD>/
        <HHMMSS>_<task-id>/
          task.json
          config.<native-format>
```

Do not add separate history, drafts, or backup directories in this phase.
Configuration backup files may live alongside their original files.
Model weights, datasets, previews, logs, and trained outputs remain in their
existing locations. Task records reference them without duplicating large files.

## Settings and Credentials

settings.json has schema_version and a revision for conflict detection. It owns:

- Default engine, remember-selection preference, engine ordering.
- Shared UI preferences, excluding ephemeral menus and dialogs.
- Default training model paths and common dataset/output paths.
- Tagging model paths keyed by stable model ID, including locally supported
  natural-language captioning models. Do not introduce new tagging engines.
- Engine Python path overrides; preserve environment validation.
- Download source and proxy preferences.
- Default preset selection keyed by model, engine, and training target.
- GUI, monitor, and TensorBoard startup configuration.
- API provider configuration and credential references, but not secret values.

Relative filesystem paths resolve against the project root, never the shell cwd.
Explicit task inputs win over configured default model/tagger paths. Changing a
default path does not move files or rewrite saved tasks and presets.

auth.json stores API credentials. Secret values are write-only through the GUI
API; reads expose configured state and masked metadata. Do not include secrets
in settings exports, presets, task snapshots, errors, or logs. Restrict file
permissions where supported; plaintext file separation is not encryption.

Use validated, bounded field updates, revision checks, and atomic replacement.
Keep a last-known-good configuration backup. Corrupt files must not silently be
overwritten by defaults. Concurrent edits must report a conflict rather than
silently overwrite newer settings. UI save failures must remain visible.
No generic arbitrary-path write API is permitted.

## Startup and Port Ownership

Priority: explicit CLI options > settings.json > program defaults.
Existing CLI flags remain compatible. GUI edits to startup settings take effect
on restart; do not unexpectedly stop a running server.

GUI defaults: loopback host, port 28000, conflict policy error.
Cloud deployment can explicitly choose 0.0.0.0, port 6006, no browser launch.
Public listening requires an access-protection warning and existing server or
deployment authentication; this project does not add a full account system here.

Supported conflict policies:

- error: stop startup of the affected service with a clear reason.
- next_available: search a bounded range, skipping every reserved service port.
- disable: skip an auxiliary service with a warning; not valid for the main GUI.

Reserve the GUI endpoint before allocating auxiliary services. Duplicate requested
ports must be detected before spawning processes. TensorBoard and monitor must
never claim the GUI port, including through fallback selection. When the GUI asks
for 6006, TensorBoard's previous default of 6006 is not a reason to move the GUI.
Apply the auxiliary service's configured conflict policy instead.

No automatic termination of processes that occupy ports. A port probe alone does
not prove that an existing listener is this application. Report an existing GUI
only after verifying its identity. Handle the bind race after availability checks
with visible errors and child-process cleanup.

Keep monitoring under the GUI's existing integrated route. An internal monitor
process, where currently necessary, must use a distinct loopback endpoint and must
not be presented as an additional public port. TensorBoard remains optional.
Expose only actually started service addresses to the UI.

## Presets

User-created presets and named complete training configurations share presets/.
Built-in presets remain versioned application resources. Editing a built-in preset
creates a user copy. User default mappings point to stable user preset IDs, not
unvalidated paths.

Selection priority: explicitly imported/reused task parameters > user default
preset > built-in defaults. Loading server preferences must not overwrite edited
form state. Preserve the existing import validation and export normalization.

Provide an explicit one-time migration for old settings and user presets, with a
preview/confirmation and no overwrite of existing server data. Do not automatically
copy browser data or erase legacy storage.

## Task Archives

Only tasks created after this feature use tasks/. Do not migrate or delete old
history. Reuse existing task scheduling, cancellation, logging, and status APIs;
do not create a second scheduler or automatically resume archived training.

For each new training task:

1. Validate and prepare the final native engine configuration.
2. Persist task identity and configuration before launching training. Failure to
   save the required snapshot prevents launch and is reported to the user.
3. Record creation/start/end times, model, target, engine, status, output directory,
   actual output files, preview references, log reference, and failure reason.
4. Keep the submitted configuration immutable; update task metadata atomically.
5. Reconcile process identity on restart, including PID reuse protection. Never
   infer success from a missing process. Uncertain execution state remains explicit.

Use server-local date folders and timestamps with timezone offsets in task.json.
Task IDs prevent filename collisions. Preserve the engine's TOML/YAML/JSON format.
Actual credential values must never appear in archived engine configurations.

Task UI reads the server records and supports parameter reuse, save-as-preset,
logs, preview, and output references. Missing external artifacts are shown as
missing, not as a broken task list. Deleting a record does not delete external
artifacts; deleting outputs requires a separate explicit confirmation.

Existing code already persists task queue/history in logs/task_queue.json.
Integration must preserve scheduler behavior while making new per-task archives
authoritative for their configuration and metadata; the queue remains an execution
index, not another independently edited archive.

## Delivery Slices

1. Storage foundation and startup port arbitration, with regression tests.
2. Existing global preference, credential, path, and preset consumers connected
   end-to-end, including local tagging model path overrides.
3. New task archives and task-page integration, without old-history migration.

Use additive internal modules and existing APIs where possible. Update and portable
package procedures must preserve user_data; add Git exclusion and ensure no real
user credentials or files are committed. No main merge or release in this scope.

## Acceptance

- GUI 6006 with TensorBoard requesting 6006: GUI stays on 6006; auxiliary policy is
  obeyed; no duplicate listener, wrong monitor page, or silent GUI fallback.
- Occupied GUI port, disabled auxiliaries, exhausted fallback ranges, identical
  requested ports, and bind failures all produce deterministic tested outcomes.
- Explicit CLI overrides saved startup values; different working directories do
  not change data paths.
- Browser/port changes and backend restart retain shared settings and presets.
- Invalid JSON, write failures, concurrent edits, and invalid/traversal preset IDs
  do not destroy user data.
- Credential reads/exports/tasks/logs do not disclose stored keys.
- Tagger consumes configured local model paths; per-operation explicit paths win.
- New training task records reference the actual submitted native configuration,
  output and previews; failed/cancelled tasks remain inspectable after restart.
- Existing import, default selection, task queue, stop, log, and preview regressions
  pass. Frontend check and relevant backend tests pass; inspect real GUI and run a
  bounded available-engine training smoke test before claiming end-to-end success.
- Independent review before merging to dev. Report any missing validation; the
  desired date does not waive these checks.
