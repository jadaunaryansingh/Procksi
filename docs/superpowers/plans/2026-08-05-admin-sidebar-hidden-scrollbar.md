# Admin Sidebar Hidden Scrollbar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hide the admin sidebar scrollbar without disabling sidebar scrolling.

**Architecture:** Define one cross-browser CSS utility in the admin application's global stylesheet, then opt the sidebar navigation container into it. Keep `overflow-y-auto` as the scrolling mechanism.

**Tech Stack:** React, Tailwind CSS v4, CSS

## Global Constraints

- Change only the admin sidebar scrollbar presentation.
- Preserve wheel, trackpad, touch, and keyboard scrolling.
- Support Firefox, Chromium, Safari, and legacy Microsoft scrollbar properties.

---

### Task 1: Hide the sidebar scrollbar

**Files:**
- Modify: `apps/admin/src/index.css`
- Modify: `apps/admin/src/components/Sidebar.jsx:73`

**Interfaces:**
- Consumes: the existing sidebar `<nav>` with `overflow-y-auto`
- Produces: a `scrollbar-hide` CSS utility applied only to that `<nav>`

- [ ] **Step 1: Verify the utility is absent**

Run: `rg -n "scrollbar-hide|scrollbar-width|-ms-overflow-style" apps/admin/src/index.css apps/admin/src/components/Sidebar.jsx`
Expected: no `scrollbar-hide` utility or class is found.

- [ ] **Step 2: Add the cross-browser utility**

Append to `apps/admin/src/index.css`:

```css
@utility scrollbar-hide {
  -ms-overflow-style: none;
  scrollbar-width: none;

  &::-webkit-scrollbar {
    display: none;
  }
}
```

- [ ] **Step 3: Apply it to the sidebar navigation**

Change the `<nav>` class list to:

```jsx
<nav className="flex-1 px-3 space-y-1 mt-2 overflow-y-auto overflow-x-hidden pb-4 scrollbar-hide">
```

- [ ] **Step 4: Verify source and production build**

Run: `rg -n "scrollbar-hide|scrollbar-width|-ms-overflow-style" apps/admin/src/index.css apps/admin/src/components/Sidebar.jsx`
Expected: all browser rules and the sidebar class are present.

Run: `npm run build`
Expected: exit code 0.
