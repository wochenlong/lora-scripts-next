# Engine Management List Design

## Scope

Improve the existing training engine settings page with a compact list,
search, installation filters, and persistent user ordering. Preserve the
current rounded visual language, light/dark themes, and lifecycle operations.
The psutil dependency fix is a separate change.

## Layout

- Keep the existing settings navigation and global engine preferences.
- Place a search input and All / Installed / Not installed segmented filter
  above the list, with the visible result count.
- Use compact rows with a drag handle, existing engine mark, name, explicit
  runtime status, supported-model tags, primary lifecycle action, and menu.
- Put the summary, version, update metadata, runtime paths, and secondary
  lifecycle actions in the existing engine management detail surface.
- Keep the default-engine badge visually secondary. Display installation
  status independently, including for Kohya.
- Reuse Element Plus icons and existing feature CSS/tokens. Narrow screens
  wrap tags and toolbar controls without horizontal overflow.
- Paginate at a fixed five engines per page; hide pagination when results fit
  on one page. Search/filter the complete catalog before slicing the page.
  Changing search/filter resets to page one; status changes clamp the page.
  No virtualization in this iteration.

## Search And Filters

Search the localized engine name, engine ID, summary, and localized capability
tags case-insensitively after trimming whitespace. Search and status filters
combine; an empty result offers a clear-filters action.

Installed includes ready and installed_unverified. Not installed includes only
not_installed. Unknown, installing, auditing, broken, disabled, and coming_soon
remain visible under All, with their actual status; do not imply that these
states prove whether runtime files exist.

## Ordering

- Dragging starts only from the handle, not from action buttons or the row.
- A drop inserts the dragged engine before the target engine in the complete
  ordered catalog. Dropping on itself is a no-op.
- Filtering does not disable sorting. Hidden entries retain their relative
  order; the visible dragged item moves relative to the visible target in the
  complete list. Clearing filters reveals that complete order.
- The menu offers Move to top, Move up, and Move down as keyboard/touch
  alternatives. Up/down use adjacent visible items as destinations.
- Provide Restore default order as a list-level menu action.
- Dragging and adjacent moves stay within the current page. Move to top moves
  to the global first position and returns to page one, as does restoring order.
- Persist only engine IDs under a dedicated browser-local storage key,
  separate from nt.training.enginePrefs.
- Normalize saved data: remove duplicates and obsolete IDs, append new catalog
  IDs in catalog order, and fall back to catalog order for malformed data.
- Storage failure must not break the page. Keep the current in-memory order
  and show a save-failure message.
- Ordering is a preference for this browser origin, not server-wide or
  synchronized across devices.
- Sorting never changes the default engine or remembered training selections.
- Status polling must not reset the order. Lifecycle operations continue to
  target engine IDs, not visual indices.

## Implementation Boundaries

- frontend/src/pages/EnginesSettingsPage.vue: toolbar, filtered ordered view,
  drag/menu events, existing lifecycle coordination.
- frontend/src/engines/listPreferences.ts: normalization, move operations,
  and guarded persistence, with adjacent unit tests.
- Existing settings feature stylesheet: compact responsive rows and drag
  feedback, without unrelated layout changes.
- Existing English and Chinese locale files: labels, tooltips, empty state,
  and persistence error text.
- Reuse existing status API, dialogs, polling, SSE, and confirmations. No new
  backend API, engine installation logic, or catalog architecture is required.

## Acceptance

- Unit tests cover malformed storage, duplicate/stale IDs, appended engines,
  move before target, no-op moves, filtered ordering, and storage failure.
- Component tests cover search/filter composition, empty state, all engine
  statuses, ordering actions, and preservation of training preferences.
- Verify drag sorting and reload persistence in the browser.
- Verify menu sorting with keyboard and touch-friendly controls.
- Verify desktop and narrow layouts, light/dark themes, and long names.
- Run npm run check; report existing warnings separately.
- Inspect installation/manage controls without downloading or uninstalling
  engines as part of this UI-only acceptance.

## Non-Goals

Changing the product default engine, cross-device synchronization, pinning,
automatic usage-based ordering, paginated drag sorting, and complete
install/uninstall acceptance are outside this change.
