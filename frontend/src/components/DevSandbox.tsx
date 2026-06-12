import { useState } from 'react';
import { Box, Card, CardContent, Typography, Button, Alert, Paper } from '@mui/material';
import { Science, CheckCircle, Warning, Cancel } from '@mui/icons-material';
import axios from 'axios';

interface DevSandboxProps {
  token: string;
  backendUrl: string;
  onInjectionSuccess: (loanId: string) => void;
}

export default function DevSandbox({ token, backendUrl, onInjectionSuccess }: DevSandboxProps) {
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const injectProfile = async (profileType: 'positive' | 'medium' | 'negative') => {
    setLoading(true);
    setStatus(null);

    try {
      const res = await axios.post(
        `${backendUrl}/api/test-cases/inject`,
        { profileType, loanAmount: 65000 },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      setStatus({ type: 'success', message: res.data.message });
      if (res.data.loanId) {
        onInjectionSuccess(res.data.loanId);
      }
    } catch (err: any) {
      console.error(err);
      setStatus({ type: 'error', message: err.response?.data?.error || 'Injection failed.' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box component="div" sx={{ p: 3 }}>
      <Box component="div" sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
        <Science sx={{ fontSize: 36, color: '#6366f1' }} />
        <Typography variant="h4" sx={{ fontWeight: 'bold' }}>Developer Sandbox</Typography>
      </Box>

      <Typography variant="body1" sx={{ color: 'var(--text-secondary)', mb: 4 }}>
        Instantly seed PostgreSQL with synthetic application files and profiles. This triggers the pg-boss background worker, executing the 11 modular engines in real-time.
      </Typography>

      {status && (
        <Alert severity={status.type} sx={{ mb: 4, bgcolor: status.type === 'success' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)', color: status.type === 'success' ? '#10b981' : '#f43f5e' }}>
          {status.message}
        </Alert>
      )}

      {/* Responsive Grid layout using clean, CSS flexbox */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '24px' }}>
        {/* 1. Positive Case */}
        <div style={{ flex: '1 1 300px' }}>
          <Card className="glass-panel" sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            <CardContent sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Box component="div" sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <CheckCircle sx={{ color: '#10b981', fontSize: 32 }} />
                <Typography variant="h5" sx={{ fontWeight: 'bold' }}>Positive Profile</Typography>
              </Box>
              
              <Typography variant="body2" sx={{ color: 'var(--text-secondary)' }}>
                Generates a clean synthetic profile with matching Aadhaar/PAN fields, high CIBIL (780), verified employment with Fintech Innovators, and low DTI ratio.
              </Typography>

              <Paper variant="outlined" sx={{ p: 2, bgcolor: 'rgba(255,255,255,0.02)', borderColor: 'rgba(255,255,255,0.05)', color: 'var(--text-secondary)' }}>
                <Typography variant="caption" sx={{ display: 'block' }}>✓ KYC: Name/DOB Matches</Typography>
                <Typography variant="caption" sx={{ display: 'block' }}>✓ Income: Verified (Rs. 85,000)</Typography>
                <Typography variant="caption" sx={{ display: 'block' }}>✓ CIBIL Score: 780 (Excellent)</Typography>
                <Typography variant="caption" sx={{ display: 'block' }}>✓ Fraud Flags: None</Typography>
                <Typography variant="caption" sx={{ display: 'block' }}>✓ Expected Output: **APPROVE**</Typography>
              </Paper>

              <Box component="div" sx={{ mt: 'auto' }}>
                <Button
                  variant="contained"
                  fullWidth
                  disabled={loading}
                  onClick={() => injectProfile('positive')}
                  sx={{ bgcolor: '#10b981', '&:hover': { bgcolor: '#059669' }, textTransform: 'none', fontWeight: 'bold' }}
                >
                  Inject Positive Case
                </Button>
              </Box>
            </CardContent>
          </Card>
        </div>

        {/* 2. Medium-Risk Case */}
        <div style={{ flex: '1 1 300px' }}>
          <Card className="glass-panel" sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            <CardContent sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Box component="div" sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <Warning sx={{ color: '#f59e0b', fontSize: 32 }} />
                <Typography variant="h5" sx={{ fontWeight: 'bold' }}>Medium-Risk Profile</Typography>
              </Box>

              <Typography variant="body2" sx={{ color: 'var(--text-secondary)' }}>
                Generates a profile containing minor document name variations (e.g. Jonny vs Jane), an average credit score (640), and an elevated debt exposure (50% DTI).
              </Typography>

              <Paper variant="outlined" sx={{ p: 2, bgcolor: 'rgba(255,255,255,0.02)', borderColor: 'rgba(255,255,255,0.05)', color: 'var(--text-secondary)' }}>
                <Typography variant="caption" sx={{ display: 'block' }}>⚠ KYC: Minor Name Deviation</Typography>
                <Typography variant="caption" sx={{ display: 'block' }}>✓ Income: Verified (Rs. 50,000)</Typography>
                <Typography variant="caption" sx={{ display: 'block' }}>⚠ CIBIL Score: 640 (Average)</Typography>
                <Typography variant="caption" sx={{ display: 'block' }}>⚠ DTI: 50% (Medium Risk)</Typography>
                <Typography variant="caption" sx={{ display: 'block' }}>✓ Expected Output: **MANUAL REVIEW**</Typography>
              </Paper>

              <Box component="div" sx={{ mt: 'auto' }}>
                <Button
                  variant="contained"
                  fullWidth
                  disabled={loading}
                  onClick={() => injectProfile('medium')}
                  sx={{ bgcolor: '#f59e0b', '&:hover': { bgcolor: '#d97706' }, textTransform: 'none', fontWeight: 'bold' }}
                >
                  Inject Medium-Risk Case
                </Button>
              </Box>
            </CardContent>
          </Card>
        </div>

        {/* 3. Negative Case */}
        <div style={{ flex: '1 1 300px' }}>
          <Card className="glass-panel" sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            <CardContent sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Box component="div" sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <Cancel sx={{ color: '#f43f5e', fontSize: 32 }} />
                <Typography variant="h5" sx={{ fontWeight: 'bold' }}>Negative Profile</Typography>
              </Box>

              <Typography variant="body2" sx={{ color: 'var(--text-secondary)' }}>
                Generates a fraudulent application signature. Submits mismatched document parameters, invalid company listings, high debt utilization, and a poor bureau history.
              </Typography>

              <Paper variant="outlined" sx={{ p: 2, bgcolor: 'rgba(255,255,255,0.02)', borderColor: 'rgba(255,255,255,0.05)', color: 'var(--text-secondary)' }}>
                <Typography variant="caption" sx={{ display: 'block' }}>✕ KYC: ID Numbers Mismatch</Typography>
                <Typography variant="caption" sx={{ display: 'block' }}>✕ Income: Fake Employer Company</Typography>
                <Typography variant="caption" sx={{ display: 'block' }}>✕ CIBIL Score: 450 (Very Poor)</Typography>
                <Typography variant="caption" sx={{ display: 'block' }}>✕ Fraud flags: Circular Transactions</Typography>
                <Typography variant="caption" sx={{ display: 'block' }}>✓ Expected Output: **REJECT**</Typography>
              </Paper>

              <Box component="div" sx={{ mt: 'auto' }}>
                <Button
                  variant="contained"
                  fullWidth
                  disabled={loading}
                  onClick={() => injectProfile('negative')}
                  sx={{ bgcolor: '#f43f5e', '&:hover': { bgcolor: '#e11d48' }, textTransform: 'none', fontWeight: 'bold' }}
                >
                  Inject Negative Case
                </Button>
              </Box>
            </CardContent>
          </Card>
        </div>
      </div>
    </Box>
  );
}
