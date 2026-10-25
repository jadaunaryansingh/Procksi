import { createContext } from 'react';

// The context object lives in its own module so that AuthContext.jsx can export
// only the provider component and useAuth.js only the hook. Vite's Fast Refresh
// requires a file to export components exclusively to preserve state on edit.
export const AuthContext = createContext();
