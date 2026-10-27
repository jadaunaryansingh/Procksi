// Which email addresses may sign in. Set per deployment; nothing here names an
// institution. Unset VITE_ALLOWED_EMAIL_DOMAIN rejects every address (fail closed).
export const ALLOWED_EMAIL_DOMAIN = (import.meta.env.VITE_ALLOWED_EMAIL_DOMAIN || '')
    .trim()
    .replace(/^@/, '')
    .toLowerCase();
export const ALLOWED_EMAIL_SUFFIX = `@${ALLOWED_EMAIL_DOMAIN}`;
export const MASTER_ADMIN_EMAIL = (import.meta.env.VITE_MASTER_ADMIN_EMAIL || '').trim().toLowerCase();
export const EMAIL_DOMAIN_ERROR = `Only ${ALLOWED_EMAIL_SUFFIX} email addresses are permitted.`;

export const isAllowedEmail = (email) =>
    !!ALLOWED_EMAIL_DOMAIN && String(email || '').trim().toLowerCase().endsWith(ALLOWED_EMAIL_SUFFIX);

export const emailPlaceholder = (local) => `${local}@${ALLOWED_EMAIL_DOMAIN || 'example.edu'}`;
