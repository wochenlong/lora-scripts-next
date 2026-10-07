# User Data

Implementation tracking: issue #405. This delivery includes settings persistence,
preset CRUD and new task configuration archives, not the entire preference migration.

The project-root `user_data/` directory holds server-owned settings. It is ignored
by Git and excluded from portable copy/update operations. Relative paths are
resolved against the project directory.

## Startup

Create `user_data/settings.json` with the sections you need. Omitted values use
application defaults; an explicit CLI option overrides the corresponding file
setting. Restart the GUI after changing startup options.

Example for a cloud deployment exposing port 6006:

```json
{
  "schema_version": 1,
  "revision": 0,
  "startup": {
    "gui": {
      "host": "0.0.0.0",
      "port": 6006,
      "open_browser": false,
      "port_conflict": "error"
    },
    "monitor": {
      "enabled": true,
      "mode": "integrated",
      "port": 6008,
      "port_conflict": "next_available"
    },
    "tensorboard": {
      "enabled": false,
      "host": "127.0.0.1",
      "port": 6007,
      "port_conflict": "disable"
    }
  },
  "paths": {
    "tagger_models": {
      "wd-eva02-large-tagger-v3": "./tagger-models/wd14/wd-eva02-large-tagger-v3"
    }
  }
}
```

GUI defaults to `127.0.0.1:28000`, conflict policy `error`.
TensorBoard is optional and disabled by default; enable it in the file or with
`--enable-tensorboard`. Monitor runs on an internal loopback endpoint behind the
GUI integration. Exposing the GUI does not require exposing its monitor port.

`error` stops startup on a conflict. `next_available` checks at most 20 ports and
reports the actual selected port; it skips reserved service ports. `disable`
skips an auxiliary service and emits a warning; it cannot disable the main GUI.
The GUI owns its selected port before any auxiliary service is allocated. No
unrelated listener is terminated.

Do not expose this service directly to an untrusted network. Use an authenticated
reverse proxy or equivalent deployment protection. File-backed settings do not
introduce a multi-user account or authentication system.

## Local Tagging Model Paths

`paths.tagger_models` maps the existing tagging model ID to a local asset
directory, not to one weight file. The directory must contain the files expected
by that model (for example `model.onnx` and `selected_tags.csv` for WD models).
Weights are not copied into user_data.

The explicit `MIKAZUKI_TAGGER_MODELS_DIR` environment override retains priority.
Restart or unload an already loaded tagger after changing its directory.

## Durable File Contract

Settings writes validate a bounded schema, check the revision, serialize writers,
and atomically replace the file. `settings.json.bak` retains the preceding valid
settings. A corrupt configuration is reported and not overwritten with defaults.
Keep the application stopped while manually editing files; API writes use
revision checks and should be used for concurrent clients.

`auth.json` is reserved for API credentials. The API returns only configured
provider flags, never secret values. Ordinary exports must not include this file.
POSIX temporary-file permissions restrict access; Windows protection also depends
on the directory ACL. This file is not encrypted. Do not share a full user_data
backup without first considering its credentials.

The initial API exposes `/api/user-data/settings` (GET/PATCH) and
`/api/user-data/auth` (GET metadata) plus `PUT /api/user-data/auth/{provider}`.
Writes require JSON and an expected revision. Errors never echo secret values.
The credential store is infrastructure only until existing provider adapters are
explicitly migrated; do not assume all old API-key settings already use it.

## Rollout Boundary

Default engine, per-model remembered engine and engine list ordering now use the
settings API. The frontend loads them before initial routing. Failed saves remain
visible; concurrent edits refresh server settings and require another user action,
rather than silently overwriting the other client.

The engine settings page offers an explicit, confirmed import of old browser
engine preferences when the corresponding server fields do not exist. Import does
not delete browser data or overwrite existing server fields. Other browser
preferences remain subsequent tracked steps in #405.
No old task history is copied or deleted by this delivery.

## Presets and Task Configuration Archives

User presets are JSON files in `user_data/presets/`. The task detail page can save
task parameters as a preset and edit or delete saved presets. The API provides
GET/POST `/api/user-data/presets` and GET/PATCH/DELETE
`/api/user-data/presets/{id}`. A preset referenced by `default_presets` cannot be
deleted. Applying that default automatically in training is not yet connected.

New configuration snapshots are stored in
`user_data/tasks/<engine>/<YYYY-MM-DD>/<HHMMSS>_<task-id>/`, using UTC timestamps.
Each contains `task.json` and a sanitized configuration snapshot. When supplied,
`engine_config_path` is also captured as `engine-config.yaml` or JSON alongside
the UI configuration. Credential fields are removed recursively before writing
snapshots; original training files are not modified. A missing or invalid source
blocks task registration. Snapshots are reserialized, so comments are not retained.
The task-page header offers archive browsing even after queue history is cleared;
task details additionally offer filtered selection and parameter import into the matching training page.
GET `/api/user-data/task-archives` returns `data.archives`; preset lists return
`data.presets`. Archive detail is available at `/api/user-data/task-archives/{id}`.

These are configuration snapshots, not a replacement for the existing task
lifecycle store or a backup of output models and preview images. Existing task
history is left untouched. Back up `user_data/` separately before upgrades.

Runtime model/Python/default-preset path fields are reserved typed settings until
the owning consumer is explicitly connected.
Do not treat a settings field's presence as proof that its consumer is migrated.
