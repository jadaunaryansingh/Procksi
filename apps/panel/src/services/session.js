export const getStoredUserInfo = () => {
  try {
    return JSON.parse(localStorage.getItem('user_info') || '{}');
  } catch {
    return {};
  }
};

export const requirePanelId = () => {
  const userInfo = getStoredUserInfo();
  if (!userInfo.panel_id) {
    throw new Error('Panel assignment missing. Please login again.');
  }
  return userInfo.panel_id;
};

/** Returns the mentor's display name (e.g. "Dr. Ankur Rai Sir") or null. */
export const getMentorName = () => {
  return getStoredUserInfo().mentor_name || null;
};

/**
 * Short initials derived from the mentor name (preferred) or panel ID.
 * Used for the avatar badge in the sidebar / header.
 */
export const panelInitials = (panelId) => {
  const name = getMentorName();
  if (name) {
    // Build initials from the name words (skip honorifics like Dr./Mr./Ms./Prof.)
    const honorifics = new Set(['dr', 'mr', 'ms', 'mrs', 'prof', 'sir']);
    const parts = name
      .split(/[\s.]+/)
      .filter(Boolean)
      .filter(p => !honorifics.has(p.toLowerCase()));
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    if (parts.length === 1) {
      return parts[0].slice(0, 2).toUpperCase();
    }
  }
  if (!panelId) return 'PNL';
  return String(panelId).replace(/[^A-Za-z0-9]/g, '').slice(0, 3).toUpperCase() || 'PNL';
};
