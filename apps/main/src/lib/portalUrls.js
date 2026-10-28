// Where the "Enter Workspace" cards point.
//
// The landing page is served from its own production host (https://www.procksi.in) and from
// localhost:3004 in development, and each portal is a separate origin in both
// cases.
//
// Resolution order:
//   1. VITE_<NAME>_PORTAL_URL (per-deployment override)
//   2. the local dev port when running on localhost
//   3. default production domain on procksi.in
const LOCAL_PORTS = {
    student: 3002,
    admin: 3000,
    panel: 3001,
    mentor: 3003,
    main: 3004,
};

const PROD_URLS = {
    student: 'https://student.procksi.in',
    admin: 'https://admin.procksi.in',
    panel: 'https://panel.procksi.in',
    mentor: 'https://mentor.procksi.in',
    main: 'https://www.procksi.in',
};

const isLocalHost = () =>
    typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

export function portalUrl(name) {
    const override = import.meta.env[`VITE_${name.toUpperCase()}_PORTAL_URL`];
    if (override) return override;
    if (isLocalHost()) return `http://localhost:${LOCAL_PORTS[name]}`;
    return PROD_URLS[name] || '#';
}
