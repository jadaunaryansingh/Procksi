// Where the "Enter Workspace" cards point.
//
// The landing page is served from its own production host and from
// localhost:3004 in development, and each portal is a separate origin in both
// cases. A hardcoded http://localhost:3002 shipped to production and sent every
// student on the live site to their own machine.
//
// Resolution order matches getApiBaseUrl() elsewhere in this app:
//   1. VITE_<NAME>_PORTAL_URL (set per deployment; no production host is hardcoded)
//   2. the local dev port when running on localhost
const LOCAL_PORTS = {
    student: 3002,
    admin: 3000,
    panel: 3001,
    mentor: 3003,
};

const isLocalHost = () =>
    typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

export function portalUrl(name) {
    const override = import.meta.env[`VITE_${name.toUpperCase()}_PORTAL_URL`];
    if (override) return override;
    if (isLocalHost()) return `http://localhost:${LOCAL_PORTS[name]}`;
    return '#';
}
