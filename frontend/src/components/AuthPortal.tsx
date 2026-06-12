import React, { useState } from 'react';
import { Box, Card, CardContent, Typography, TextField, Button, Tabs, Tab, Alert, CircularProgress } from '@mui/material';
import axios from 'axios';

interface AuthPortalProps {
  onAuthSuccess: (token: string, user: { id: number; name: string; email: string; role: 'user' | 'admin' }) => void;
  backendUrl: string;
}

export default function AuthPortal({ onAuthSuccess, backendUrl }: AuthPortalProps) {
  const [tabValue, setTabValue] = useState(0); // 0 = Login, 1 = Register
  const [role, setRole] = useState<'user' | 'admin'>('user');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
    setError('');
  };

  const handleRoleChange = (selectedRole: 'user' | 'admin') => {
    setRole(selectedRole);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (tabValue === 0) {
        // Login
        const res = await axios.post(`${backendUrl}/api/auth/login`, { email, password });
        onAuthSuccess(res.data.token, res.data.user);
      } else {
        // Register
        const res = await axios.post(`${backendUrl}/api/auth/register`, { name, email, password, role });
        onAuthSuccess(res.data.token, res.data.user);
      }
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.error || 'Authentication failed. Please verify credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box component="div" sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '90vh' }}>
      <Card className="glass-panel" sx={{ width: '100%', maxWidth: 450, p: 2, background: 'rgba(17, 24, 39, 0.85)' }}>
        <CardContent>
          <Box component="div" sx={{ display: 'flex', justifyContent: 'center', mb: 3 }}>
            <Typography variant="h4" className="gradient-text" sx={{ fontWeight: '800' }}>
              OnboardTrust AI
            </Typography>
          </Box>

          <Tabs value={tabValue} onChange={handleTabChange} variant="fullWidth" sx={{ mb: 3 }} textColor="primary" indicatorColor="primary">
            <Tab label="Login" sx={{ color: '#9ca3af', '&.Mui-selected': { color: '#818cf8' } }} />
            <Tab label="Sign Up" sx={{ color: '#9ca3af', '&.Mui-selected': { color: '#818cf8' } }} />
          </Tabs>

          {error && <Alert severity="error" sx={{ mb: 2, bgcolor: 'rgba(244, 63, 94, 0.15)', color: '#f43f5e' }}>{error}</Alert>}

          <form onSubmit={handleSubmit}>
            {tabValue === 1 && (
              <TextField
                label="Full Name"
                fullWidth
                variant="outlined"
                margin="normal"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            )}

            <TextField
              label="Email Address"
              type="email"
              fullWidth
              variant="outlined"
              margin="normal"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />

            <TextField
              label="Password"
              type="password"
              fullWidth
              variant="outlined"
              margin="normal"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />

            {tabValue === 1 && (
              <Box component="div" sx={{ mt: 2, mb: 2 }}>
                <Typography variant="body2" sx={{ color: '#9ca3af', mb: 1 }}>Select System Role:</Typography>
                <Box component="div" sx={{ display: 'flex', gap: 2 }}>
                  <Button
                    type="button"
                    variant={role === 'user' ? 'contained' : 'outlined'}
                    color="primary"
                    fullWidth
                    onClick={() => handleRoleChange('user')}
                    sx={{ textTransform: 'none' }}
                  >
                    Customer
                  </Button>
                  <Button
                    type="button"
                    variant={role === 'admin' ? 'contained' : 'outlined'}
                    color="primary"
                    fullWidth
                    onClick={() => handleRoleChange('admin')}
                    sx={{ textTransform: 'none' }}
                  >
                    Administrator
                  </Button>
                </Box>
              </Box>
            )}

            <Button
              type="submit"
              variant="contained"
              fullWidth
              size="large"
              disabled={loading}
              sx={{ mt: 3, mb: 1, bgcolor: '#6366f1', '&:hover': { bgcolor: '#4f46e5' }, textTransform: 'none', fontWeight: 'bold' }}
            >
              {loading ? <CircularProgress size={24} color="inherit" /> : tabValue === 0 ? 'Sign In' : 'Create Account'}
            </Button>
          </form>

          <Box component="div" sx={{ mt: 2, textAlign: 'center' }}>
            <Typography variant="caption" sx={{ color: 'var(--text-muted)' }}>
              Demo Credentials:<br />
              User: user@digital-loan.com / user123<br />
              Admin: admin@digital-loan.com / admin123
            </Typography>
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
}
