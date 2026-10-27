/**
 * ProcksiChatRoute
 *
 * Route guard for Procksi Chat. Renders the page when the feature is on for this
 * portal, and redirects otherwise.
 *
 * A component rather than an inline ternary because the decision now comes
 * from a hook (build flag AND the coordinator's per-portal switch), and hooks
 * cannot be called in a route element expression.
 *
 * While the switch is still being read, useProcksiChatEnabled returns the build
 * flag, so this never flashes a redirect before settling.
 */
import { Navigate } from 'react-router-dom';
import { useProcksiChatEnabled } from '../hooks/useProcksiChatEnabled';

export default function ProcksiChatRoute({ children }) {
    const enabled = useProcksiChatEnabled();
    return enabled ? children : <Navigate to="/mentor" replace />;
}
