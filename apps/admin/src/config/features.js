/**
 * Feature flags for this portal.
 *
 * Procksi Chat is enabled in local development only. `import.meta.env.DEV` is true
 * under `vite dev` and false in the production build, so the deployed portals
 * keep the sidebar entry greyed out and the route redirecting while local work
 * on the feature continues.
 *
 * VITE_PROCKSI_CHAT overrides that either way: set it to "true" to force the
 * feature on (e.g. to check a production build with `vite preview`), or
 * "false" to turn it off locally. Vite inlines this at build time, so a
 * running dev server needs a restart after changing it.
 *
 * Deliberately frontend-only. The chat endpoints are still live, so this hides
 * and blocks the feature rather than securing it; anyone with a valid token
 * could still call the API directly.
 */
const override = import.meta.env.VITE_PROCKSI_CHAT;

export const PROCKSI_CHAT_ENABLED =
    override === undefined || override === ''
        ? import.meta.env.DEV
        : override === 'true';
