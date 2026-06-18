import { useState } from 'react';
import { ThemeProvider, createTheme, CssBaseline, Box, AppBar, Toolbar, Typography, Button } from '@mui/material';
import { Logout, Security, AccountCircle, Science } from '@mui/icons-material';
import AuthPortal from './components/AuthPortal';
import CustomerPortal from './components/CustomerPortal';
import AdminPortal from './components/AdminPortal';
import DevSandbox from './components/DevSandbox';
import './styles/app.css';

// Express API Backend Endpoint
const BACKEND_URL = 'http://localhost:5000';

// Custom MUI Dark Theme Config
const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#6366f1' },    // Indigo
    secondary: { main: '#10b981' },  // Emerald
    background: {
      default: '#0b0f19',
      paper: '#111827'
    },
    text: {
      primary: '#f3f4f6',
      secondary: '#9ca3af'
    }
  },
  typography: {
    fontFamily: '"Inter", "Outfit", sans-serif'
  }
});

export default function App() {
  const [token, setToken] = useState<string | null>(localStorage.getItem('loan_auth_token'));
  const [user, setUser] = useState<{ id: number; name: string; email: string; role: 'user' | 'admin' } | null>(
    JSON.parse(localStorage.getItem('loan_auth_user') || 'null')
  );
  
  const [activeLoanId, setActiveLoanId] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<'portal' | 'sandbox'>('portal');

  const handleAuthSuccess = (newToken: string, newUser: { id: number; name: string; email: string; role: 'user' | 'admin' }) => {
    localStorage.setItem('loan_auth_token', newToken);
    localStorage.setItem('loan_auth_user', JSON.stringify(newUser));
    setToken(newToken);
    setUser(newUser);
  };

  const handleLogout = () => {
    localStorage.removeItem('loan_auth_token');
    localStorage.removeItem('loan_auth_user');
    setToken(null);
    setUser(null);
    setActiveLoanId(null);
  };

  const handleSandboxInjection = (loanId: string) => {
    setActiveLoanId(loanId);
    setActiveView('portal'); // toggle to portal view tracker
  };

  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      
      {!token || !user ? (
        <AuthPortal onAuthSuccess={handleAuthSuccess} backendUrl={BACKEND_URL} />
      ) : (
        <Box component="div" sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
          {/* Header AppBar */}
          <AppBar position="static" sx={{ bgcolor: 'rgba(17, 24, 39, 0.9)', backdropFilter: 'blur(10px)', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
            <Toolbar sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Box component="div" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Security sx={{ color: '#6366f1' }} />
                <Typography variant="h6" className="gradient-text" sx={{ fontWeight: 'bold' }}>
                  OnboardTrust AI
                </Typography>
              </Box>

              <Box component="div" sx={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                {/* Navigation Toggles (Only for standard customer) */}
                {user.role === 'user' && (
                  <Box component="div" sx={{ display: 'flex', gap: 1 }}>
                    <Button
                      variant={activeView === 'portal' ? 'contained' : 'text'}
                      size="small"
                      onClick={() => setActiveView('portal')}
                      startIcon={<AccountCircle />}
                      sx={{ textTransform: 'none' }}
                    >
                      Customer Desk
                    </Button>
                    <Button
                      variant={activeView === 'sandbox' ? 'contained' : 'text'}
                      size="small"
                      onClick={() => setActiveView('sandbox')}
                      startIcon={<Science />}
                      sx={{ textTransform: 'none' }}
                    >
                      Dev Sandbox
                    </Button>
                  </Box>
                )}

                <Box component="div" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Typography variant="body2" sx={{ color: '#10b981', fontWeight: 'bold' }}>
                    {user.name} ({user.role.toUpperCase()})
                  </Typography>
                  <Button
                    variant="outlined"
                    size="small"
                    color="error"
                    onClick={handleLogout}
                    startIcon={<Logout />}
                    sx={{ textTransform: 'none' }}
                  >
                    Logout
                  </Button>
                </Box>
              </Box>
            </Toolbar>
          </AppBar>

          {/* Main Workspace slot */}
          <Box component="div" sx={{ flexGrow: 1, py: 3 }}>
            {user.role === 'admin' ? (
              <AdminPortal token={token} backendUrl={BACKEND_URL} />
            ) : activeView === 'portal' ? (
              <CustomerPortal
                token={token}
                backendUrl={BACKEND_URL}
                activeLoanId={activeLoanId}
                setActiveLoanId={setActiveLoanId}
              />
            ) : (
              <DevSandbox
                token={token}
                backendUrl={BACKEND_URL}
                onInjectionSuccess={handleSandboxInjection}
              />
            )}
          </Box>
        </Box>
      )}
    </ThemeProvider>
  );
}
