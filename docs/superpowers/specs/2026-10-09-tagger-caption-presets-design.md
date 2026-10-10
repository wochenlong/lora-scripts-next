# Tagger Caption Presets in User Data

## Goal

Persist natural-language tagger prompt templates in the server-owned `user_data`
directory instead of browser `localStorage`. Templates must remain available
across browsers, ports, portable upgrades, and user-data backups.

## Storage Contract

Reuse the existing user preset CRUD API and `user_data/presets/` records. Tagger
caption templates use:

- `train_type`: `tagger-caption`
- `name`: user-visible template name
- `description`: optional description
- `config.prompt`: prompt text
- `config.language`: output language identifier

No new backend record type or directory is introduced. Training presets remain
isolated because every tagger request lists presets with
`train_type=tagger-caption`.

## Frontend Behavior

The Tagger page loads server templates when it initializes. The built-in default
template remains frontend-owned and cannot be edited or deleted.

For server templates, the page supports:

- load the selected template;
- create a named template from the current prompt and language;
- update the selected template;
- delete the selected template;
- reset the editor to the built-in default.

Create, update, and delete operations stay busy until the API responds. Success
updates the local list from the returned record. Failure leaves the current
editor and selection intact and shows an error message.

## Legacy Migration

On the first successful server load, read the existing
`nt.tagger.captionTemplates` browser entry. Import each valid prompt as a
`tagger-caption` preset. Remove the browser entry only after every legacy
template is imported successfully.

If an import fails, keep the browser entry unchanged and retry migration on a
later page load. Imported records include a deterministic legacy marker in their
description so the frontend can avoid duplicating templates if a previous
request succeeded but the browser cleanup did not.

## Failure Policy

The server is the only persistent source after migration. The page does not
silently save new templates to `localStorage` when the backend is unavailable.
It keeps the editor usable, disables server mutations while loading, and reports
the storage error.

## Testing

Frontend tests cover:

- listing only `tagger-caption` presets;
- create, update, and delete API calls;
- conversion between preset records and prompt templates;
- successful legacy migration and browser cleanup;
- partial migration failure retaining browser data;
- component behavior for loading, updating, and deleting server templates.

Existing user-data API tests remain the backend contract coverage because this
feature uses the existing generic preset format without backend schema changes.
