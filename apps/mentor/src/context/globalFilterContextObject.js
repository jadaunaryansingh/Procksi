import { createContext } from 'react';

// The context object lives in its own module so that GlobalFilterContext.jsx
// exports only the provider component and useGlobalFilters.js only the hook.
// Vite's Fast Refresh requires a file to export components exclusively in order
// to preserve state across edits.
export const GlobalFilterContext = createContext(null);
