# Proposals Serial Number Design

## Goal

Add an `S. No.` column to the admin Project Proposals table so each visible proposal row has an immediately readable ordinal.

## Behavior

- The serial-number column is the first column in the table.
- Visible rows are numbered from `1` in their current rendered order.
- Search, semester, and status filters recalculate the visible numbering so it remains contiguous.
- An empty result continues to render one message row spanning the full table width.

## Scope

Only `apps/admin/src/pages/ProposalList.jsx` changes. No API, database, sorting, filtering, or proposal data changes are required.

## Verification

- A component/source test must fail before implementation when the `S. No.` header and visible-row index are absent.
- The test must pass after the implementation.
- The admin frontend production build must succeed.

