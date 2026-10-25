/**
 * URL guards for values that reach an `href` or an iframe `src`.
 *
 * React escapes text but does not block `javascript:` URLs in attributes — it
 * warns and renders. Student-supplied strings (proposal files, activity proof
 * links, milestone repository links) were bound straight into admin document
 * viewers, so `javascript:...` in one of those fields executed in the admin
 * origin. An iframe `src` needs no click at all: it runs on load, during the
 * routine review step.
 *
 * Mirrors the scheme allowlist already used by apps/student/src/lib/richText.js.
 */

const ALLOWED_LINK_SCHEME = /^(https?:|mailto:)/i;

/** Safe for an `href`: http(s), mailto, or a site-relative path. Else null. */
export function safeLinkUrl(url) {
    const trimmed = String(url ?? '').trim();
    if (!trimmed) return null;
    // Protocol-relative ("//evil.tld") inherits the current scheme, so it is not
    // a site-relative path and must go through the scheme check instead.
    if (trimmed.startsWith('/') && !trimmed.startsWith('//')) return trimmed;
    return ALLOWED_LINK_SCHEME.test(trimmed) ? trimmed : null;
}

/**
 * Safe for an iframe `src`: http(s) only.
 *
 * Stricter than the href guard — an embedded document should never be a
 * mailto:, a data: document (which gets its own origin but can still be used to
 * phish), or a site-relative path.
 */
export function safeFrameUrl(url) {
    const trimmed = String(url ?? '').trim();
    if (!trimmed) return null;
    return /^https?:\/\//i.test(trimmed) ? trimmed : null;
}
