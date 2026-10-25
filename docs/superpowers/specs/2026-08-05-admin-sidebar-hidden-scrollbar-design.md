# Admin Sidebar Hidden Scrollbar Design

## Goal

Hide the visible vertical scrollbar in the admin sidebar while preserving wheel, trackpad, touch, and keyboard scrolling.

## Scope

- Add one cross-browser `scrollbar-hide` utility to the admin application's global stylesheet.
- Apply that utility only to the sidebar navigation element that already owns `overflow-y-auto`.
- Do not alter sidebar dimensions, navigation items, scrolling behavior, or scrollbars elsewhere in the application.

## Browser behavior

- Firefox: use `scrollbar-width: none`.
- Legacy Microsoft engines: use `-ms-overflow-style: none`.
- Chromium and Safari: hide the `::-webkit-scrollbar` pseudo-element.

## Verification

- Build the admin application successfully.
- Confirm the sidebar navigation retains `overflow-y-auto` alongside `scrollbar-hide`.
- Confirm the utility contains all three browser-specific rules.
