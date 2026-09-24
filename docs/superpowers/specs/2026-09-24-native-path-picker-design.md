# Native Path Picker Design

## Goal

Restore the operating-system file and folder picker as the default experience on
Windows while retaining the web path browser for Linux, headless, and remote
deployments.

## User Preference

Add a path picker preference to UI settings with three values:

- `auto`: prefer the native picker when the server reports it is available,
  otherwise use the web picker.
- `native`: request the native picker first and fall back to the web picker when
  it is unavailable.
- `web`: always open the web path picker.

The default is `auto`. The preference is stored in the existing `ui-configs`
local-storage object and takes effect immediately without restarting the GUI.

## Picker Dispatch

`useServerPathPick` remains the single integration point used by schema fields,
reference paths, the tagger, and the dataset editor.

For `web`, it opens `PathPickerDialog` directly. For `auto`, it calls
`/api/pick_file` first only when the browser is connected through localhost;
remote browser hosts use the web picker. For `native`, it calls the native
endpoint even from a remote browser because the user explicitly selected it. A
successful response resolves with the selected server path. A native-picker
cancellation resolves with no path and does not open the web picker. An
unavailable native picker or other recoverable native picker failure opens the
web picker with the original mode, initial path, and filter.

The existing backend capability and picker endpoints remain unchanged. Local
versus remote access is determined from the browser hostname; server capability
remains authoritative for desktop availability. Browser user-agent detection
is not used.

An SSH tunnel can expose a remote service through `localhost`, which is
indistinguishable from a genuinely local browser connection. In that case the
user should select `Linux` (web picker) explicitly.

## Settings UI

The UI settings page displays a three-option segmented control labeled "Path
picker". Supporting text explains that automatic mode prefers the system picker
when the training host has a desktop and otherwise uses the web picker.

Saving persists the selected picker mode together with the TensorBoard URL.
Reset restores the picker mode to `auto`.

## Error Handling

The native endpoint's structured error codes distinguish cancellation,
unavailability, and native picker runtime failures. Cancellation ends the
operation. Unavailability and runtime failures fall back silently because the
web picker is the supported recovery path. Unexpected frontend request errors
also fall back to the web picker so path selection remains usable.

## Testing

Unit tests cover preference parsing and persistence, native success, native
cancellation, unavailable-native fallback, forced-web behavior, and settings
save/reset behavior. Existing component callers retain the same composable
interface.
