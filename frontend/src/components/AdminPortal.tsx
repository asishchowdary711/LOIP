import { useState, useEffect } from 'react';
import {
  Box, Typography, Card, CardContent, Button,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
  IconButton, Alert, TextField, Dialog, DialogTitle, DialogContent, DialogActions,
  Divider, List, ListItem, ListItemText, ListItemIcon,
  ToggleButton, ToggleButtonGroup
} from '@mui/material';
import {
  AppRegistration, VerifiedUser, ErrorOutlined, RateReview, CancelPresentation,
  Schedule, Sync, OpenInNew, Visibility
} from '@mui/icons-material';
import axios from 'axios';
import AnalyticsPortal from './AnalyticsPortal';

interface AdminPortalProps {
  token: string;
  backendUrl: string;
}

interface Application {
  id: string;
  loan_amount: string;
  status: string;
  risk_score: number;
  risk_category: string;
  created_at: string;
  applicant_name: string;
  recommendation: {
    recommendation: 'APPROVE' | 'MANUAL_REVIEW' | 'REJECT';
    reasons: string[];
  };
}

interface DetailReport {
  loan: {
    id: string;
    loan_amount: string;
    status: string;
    risk_score: number;
    risk_category: string;
    applicant_data: any;
    verification_matrix: any;
    recommendation: any;
    created_at: string;
  };
  documents: Array<{ id: string; document_type: string; classification_confidence: number }>;
  auditTrail: Array<{ id: string; action: string; description: string; created_at: string; actor_name?: string }>;
}

export default function AdminPortal({ token, backendUrl }: AdminPortalProps) {
  const [apps, setApps] = useState<Application[]>([]);
  const [selectedAppId, setSelectedAppId] = useState<string | null>(null);
  const [appDetail, setAppDetail] = useState<DetailReport | null>(null);
  const [viewMode, setViewMode] = useState<'queue' | 'reports'>('queue');

  // Decision Modal State
  const [actionModalOpen, setActionModalOpen] = useState(false);
  const [decisionAction, setDecisionAction] = useState<'approve' | 'reject' | 'request-docs'>('approve');
  const [comments, setComments] = useState('');
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewType, setPreviewType] = useState<string | null>(null);

  const handlePreview = async (docId: string, docType: string) => {
    try {
      const res = await axios.get(`${backendUrl}/api/documents/${docId}`, {
        headers: { Authorization: `Bearer ${token}` },
        responseType: 'blob'
      });
      const blob = new Blob([res.data], { type: (res.headers['content-type'] as string) || 'application/pdf' });
      const objectUrl = URL.createObjectURL(blob);
      setPreviewUrl(objectUrl);
      setPreviewType(docType);
    } catch (err) {
      console.error('Error fetching preview blob:', err);
    }
  };

  // Fetch applications list
  const fetchApplications = async () => {
    try {
      const res = await axios.get(`${backendUrl}/api/admin/applications`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setApps(res.data.applications);
    } catch (err) {
      console.error('Error fetching admin applications:', err);
    }
  };

  // Fetch single application detail
  const fetchDetail = async (id: string) => {
    try {
      const res = await axios.get(`${backendUrl}/api/admin/application/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setAppDetail(res.data);
    } catch (err) {
      console.error('Error fetching application detail:', err);
    }
  };

  useEffect(() => {
    fetchApplications();
  }, []);

  useEffect(() => {
    if (selectedAppId) {
      fetchDetail(selectedAppId);
    } else {
      setAppDetail(null);
    }
  }, [selectedAppId]);

  // Handle human-in-the-loop decisions
  const handleDecisionSubmit = async () => {
    if (!selectedAppId) return;
    try {
      let endpoint = `/api/admin/approve/${selectedAppId}`;
      if (decisionAction === 'reject') endpoint = `/api/admin/reject/${selectedAppId}`;
      else if (decisionAction === 'request-docs') endpoint = `/api/admin/request-documents/${selectedAppId}`;

      await axios.post(
        `${backendUrl}${endpoint}`,
        { comments },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      setActionModalOpen(false);
      setComments('');
      // Refresh
      fetchApplications();
      fetchDetail(selectedAppId);
    } catch (err) {
      console.error('Error submitting action decision:', err);
    }
  };

  // Count aggregates
  const totalCount = apps.length;
  const approvedCount = apps.filter(a => a.status === 'approved').length;
  const rejectedCount = apps.filter(a => a.status === 'rejected').length;
  const pendingCount = apps.filter(a => a.status === 'pending' || a.status === 'processing').length;
  const fraudCount = apps.filter(a => {
    const rec = a.recommendation;
    return rec?.reasons?.some(r => r.includes('Fraud') || r.includes('FRAUD'));
  }).length;

  const getScoreColor = (score: number) => {
    if (score >= 71) return '#10b981'; // Green (Low Risk / High Trust)
    if (score >= 31) return '#f59e0b'; // Amber (Medium Risk)
    return '#f43f5e'; // Red (High Risk / Low Trust)
  };

  const getRecommendationBadge = (recType: string) => {
    let color = '#f59e0b';
    if (recType === 'APPROVE') color = '#10b981';
    else if (recType === 'REJECT') color = '#f43f5e';

    return (
      <Box
        component="span"
        sx={{
          px: 1.5, py: 0.5, borderRadius: 10, fontSize: 13, fontWeight: 'bold',
          bgcolor: `${color}1e`, color
        }}
      >
        {recType || 'PENDING'}
      </Box>
    );
  };

  return (
    <Box component="div" sx={{ p: 3 }}>
      <Box component="div" sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
        <Typography variant="h4" sx={{ fontWeight: 'bold' }}>Administrative Review Portal</Typography>
        <Box component="div" sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
          <ToggleButtonGroup
            value={viewMode}
            exclusive
            onChange={(_, val) => val && setViewMode(val)}
            size="small"
            sx={{ border: '1px solid rgba(255,255,255,0.06)' }}
          >
            <ToggleButton value="queue">Review Queue</ToggleButton>
            <ToggleButton value="reports">Analytics & Reports</ToggleButton>
          </ToggleButtonGroup>
          <IconButton onClick={fetchApplications} color="primary"><Sync /></IconButton>
        </Box>
      </Box>

      {viewMode === 'reports' ? (
        <AnalyticsPortal token={token} backendUrl={backendUrl} userRole="admin" />
      ) : (
        <>

      {/* --- Section 1: Dashboard Metrics grid --- */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '20px', marginBottom: '32px' }}>
        <Card className="glass-panel" sx={{ bgcolor: 'rgba(99, 102, 241, 0.1)' }}>
          <CardContent>
            <Typography variant="body2" sx={{ color: 'var(--text-secondary)' }}>Total Applications</Typography>
            <Box component="div" sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 1 }}>
              <Typography variant="h4" sx={{ fontWeight: 'bold' }}>{totalCount}</Typography>
              <AppRegistration sx={{ color: '#6366f1' }} />
            </Box>
          </CardContent>
        </Card>

        <Card className="glass-panel" sx={{ bgcolor: 'rgba(16, 185, 129, 0.1)' }}>
          <CardContent>
            <Typography variant="body2" sx={{ color: 'var(--text-secondary)' }}>Approved</Typography>
            <Box component="div" sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 1 }}>
              <Typography variant="h4" sx={{ color: '#10b981', fontWeight: 'bold' }}>{approvedCount}</Typography>
              <VerifiedUser sx={{ color: '#10b981' }} />
            </Box>
          </CardContent>
        </Card>

        <Card className="glass-panel" sx={{ bgcolor: 'rgba(244, 63, 94, 0.1)' }}>
          <CardContent>
            <Typography variant="body2" sx={{ color: 'var(--text-secondary)' }}>Rejected</Typography>
            <Box component="div" sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 1 }}>
              <Typography variant="h4" sx={{ color: '#f43f5e', fontWeight: 'bold' }}>{rejectedCount}</Typography>
              <CancelPresentation sx={{ color: '#f43f5e' }} />
            </Box>
          </CardContent>
        </Card>

        <Card className="glass-panel" sx={{ bgcolor: 'rgba(245, 158, 11, 0.1)' }}>
          <CardContent>
            <Typography variant="body2" sx={{ color: 'var(--text-secondary)' }}>Under Review</Typography>
            <Box component="div" sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 1 }}>
              <Typography variant="h4" sx={{ color: '#f59e0b', fontWeight: 'bold' }}>{pendingCount}</Typography>
              <RateReview sx={{ color: '#f59e0b' }} />
            </Box>
          </CardContent>
        </Card>

        <Card className="glass-panel" sx={{ bgcolor: 'rgba(244, 63, 94, 0.1)' }}>
          <CardContent>
            <Typography variant="body2" sx={{ color: 'var(--text-secondary)' }}>Fraud Alerts</Typography>
            <Box component="div" sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 1 }}>
              <Typography variant="h4" sx={{ color: '#f43f5e', fontWeight: 'bold' }}>{fraudCount}</Typography>
              <ErrorOutlined sx={{ color: '#f43f5e' }} />
            </Box>
          </CardContent>
        </Card>
      </div>

      {/* --- Section 2: Split View Layout --- */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '24px' }}>
        {/* Left: Applications List */}
        <div style={{ flex: selectedAppId ? '1 1 350px' : '1 1 100%' }}>
          <Card className="glass-panel" sx={{ p: 2 }}>
            <CardContent>
              <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 2 }}>All Submissions</Typography>

              <TableContainer component={Paper} sx={{ bgcolor: 'transparent', boxShadow: 'none' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ '& th': { color: '#9ca3af', borderBottom: '1px solid rgba(255,255,255,0.05)' } }}>
                      <TableCell>Applicant</TableCell>
                      <TableCell align="right">Amount</TableCell>
                      <TableCell align="right">AI Rec</TableCell>
                      <TableCell align="right">Final Status</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {apps.map((row) => (
                      <TableRow
                        key={row.id}
                        hover
                        onClick={() => setSelectedAppId(row.id)}
                        selected={selectedAppId === row.id}
                        sx={{
                          cursor: 'pointer',
                          '& td': { color: '#f3f4f6', borderBottom: '1px solid rgba(255,255,255,0.05)' },
                          '&.Mui-selected': { bgcolor: 'rgba(99, 102, 241, 0.15)' }
                        }}
                      >
                        <TableCell component="th" scope="row">
                          <Typography variant="body2" sx={{ fontWeight: 'bold' }}>{row.applicant_name}</Typography>
                          <Typography variant="caption" sx={{ color: 'var(--text-muted)' }}>{new Date(row.created_at).toLocaleDateString()}</Typography>
                        </TableCell>
                        <TableCell align="right">Rs. {parseFloat(row.loan_amount).toLocaleString()}</TableCell>
                        <TableCell align="right">
                          {getRecommendationBadge(row.recommendation?.recommendation)}
                        </TableCell>
                        <TableCell align="right">
                          <Box
                            component="span"
                            sx={{
                              px: 1, py: 0.2, borderRadius: 5, fontSize: 11, fontWeight: 'bold',
                              bgcolor: row.status === 'approved' ? 'rgba(16, 185, 129, 0.15)' : row.status === 'rejected' ? 'rgba(244, 63, 94, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                              color: row.status === 'approved' ? '#10b981' : row.status === 'rejected' ? '#f43f5e' : '#f59e0b'
                            }}
                          >
                            {row.status.toUpperCase()}
                          </Box>
                        </TableCell>
                      </TableRow>
                    ))}
                    {apps.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={4} align="center" style={{ color: '#9ca3af' }}>No loan records found.</TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </div>

        {/* Right: Detailed Dashboard Review Sheet */}
        {selectedAppId && appDetail && (
          <div style={{ flex: '1 1 500px' }}>
            <Card className="glass-panel" sx={{ p: 2 }}>
              <CardContent>
                <Box component="div" sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
                  <Box component="div">
                    <Typography variant="h5" className="gradient-text" sx={{ fontWeight: 'bold' }}>
                      {appDetail.loan.applicant_data?.name}
                    </Typography>
                    <Typography variant="caption" sx={{ color: 'var(--text-muted)' }}>Application ID: {appDetail.loan.id}</Typography>
                  </Box>
                  <Button variant="outlined" size="small" onClick={() => setSelectedAppId(null)}>Close Pane</Button>
                </Box>

                {/* Split container with Gauge and AI recommendation highlights */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '24px', marginBottom: '32px' }}>
                  {/* Gauge */}
                  <div style={{ flex: '1 1 150px', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                    <Box component="div" sx={{ textAlign: 'center' }}>
                      <svg width="130" height="130" viewBox="0 0 100 100">
                        <circle cx="50" cy="50" r="40" stroke="rgba(255,255,255,0.05)" stroke-width="8" fill="none" />
                        <circle cx="50" cy="50" r="40" stroke={getScoreColor(appDetail.loan.risk_score)} stroke-width="8" fill="none"
                          stroke-dasharray="251.2" stroke-dashoffset={251.2 - (251.2 * appDetail.loan.risk_score) / 100}
                          transform="rotate(-90 50 50)" style={{ transition: 'stroke-dashoffset 1s ease-in-out' }} />
                        <text x="50" y="52" text-anchor="middle" font-size="18" fill="#f3f4f6" font-weight="bold">{appDetail.loan.risk_score}</text>
                        <text x="50" y="68" text-anchor="middle" font-size="8" fill="#9ca3af" font-weight="bold">TRUST SCORE</text>
                      </svg>
                      <Typography variant="body2" sx={{ color: getScoreColor(appDetail.loan.risk_score), fontWeight: 'bold', mt: 1 }}>
                        Category: {appDetail.loan.risk_category}
                      </Typography>
                    </Box>
                  </div>

                  {/* AI Explainable Recommendations Bullet list */}
                  <div style={{ flex: '1 1 250px' }}>
                    <Card sx={{ bgcolor: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.05)', borderRadius: 2 }}>
                      <CardContent>
                        <Box component="div" sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.5 }}>
                          <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>AI Agent Recommendation:</Typography>
                          {getRecommendationBadge(appDetail.loan.recommendation?.recommendation)}
                        </Box>
                        
                        <Typography variant="body2" sx={{ color: 'var(--text-secondary)', fontWeight: 'bold', mb: 1 }}>Justifications Breakdown:</Typography>
                        <Box component="div" sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                          {appDetail.loan.recommendation?.reasons?.map((reason: string, i: number) => (
                            <Typography key={i} variant="caption" sx={{ display: 'block', color: reason.startsWith('✓') ? '#10b981' : reason.startsWith('✕') ? '#f43f5e' : '#f59e0b' }}>
                              {reason}
                            </Typography>
                          ))}
                        </Box>
                      </CardContent>
                    </Card>
                  </div>
                </div>

                <Divider sx={{ my: 3, borderColor: 'rgba(255,255,255,0.05)' }} />

                {/* --- Section 3: Verification Matrix Details --- */}
                <Typography variant="h6" className="gradient-text" sx={{ fontWeight: 'bold', mb: 2 }}>Verification Matrices</Typography>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '32px' }}>
                  {/* Row 1 */}
                  <Paper variant="outlined" sx={{ p: 2, bgcolor: 'transparent', borderColor: 'rgba(255,255,255,0.05)' }}>
                    <Typography variant="subtitle2" sx={{ color: 'var(--text-secondary)', fontWeight: 'bold' }}>Identity & KYC Match (20%)</Typography>
                    <Box component="div" sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
                      <Typography variant="body2">Score: {appDetail.loan.verification_matrix?.identity?.score}/100</Typography>
                      <Typography variant="body2" sx={{ color: appDetail.loan.verification_matrix?.identity?.passed ? '#10b981' : '#f43f5e' }}>
                        {appDetail.loan.verification_matrix?.identity?.passed ? 'PASSED' : 'FAILED'}
                      </Typography>
                    </Box>
                  </Paper>

                  <Paper variant="outlined" sx={{ p: 2, bgcolor: 'transparent', borderColor: 'rgba(255,255,255,0.05)' }}>
                    <Typography variant="subtitle2" sx={{ color: 'var(--text-secondary)', fontWeight: 'bold' }}>Income Validation (20%)</Typography>
                    <Box component="div" sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
                      <Typography variant="body2">Score: {appDetail.loan.verification_matrix?.income?.score}/100</Typography>
                      <Typography variant="body2" sx={{ color: appDetail.loan.verification_matrix?.income?.passed ? '#10b981' : '#f43f5e' }}>
                        {appDetail.loan.verification_matrix?.income?.passed ? 'VERIFIED' : 'SUBSTANDARD'}
                      </Typography>
                    </Box>
                  </Paper>

                  {/* Row 2 */}
                  <Paper variant="outlined" sx={{ p: 2, bgcolor: 'transparent', borderColor: 'rgba(255,255,255,0.05)' }}>
                    <Typography variant="subtitle2" sx={{ color: 'var(--text-secondary)', fontWeight: 'bold' }}>Bank Statement Analysis (15%)</Typography>
                    <Box component="div" sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
                      <Typography variant="body2">Score: {appDetail.loan.verification_matrix?.bank?.score}/100</Typography>
                      <Typography variant="body2" sx={{ color: appDetail.loan.verification_matrix?.bank?.passed ? '#10b981' : '#f43f5e' }}>
                        {appDetail.loan.verification_matrix?.bank?.passed ? 'HEALTHY' : 'WARN'}
                      </Typography>
                    </Box>
                  </Paper>

                  <Paper variant="outlined" sx={{ p: 2, bgcolor: 'transparent', borderColor: 'rgba(255,255,255,0.05)' }}>
                    <Typography variant="subtitle2" sx={{ color: 'var(--text-secondary)', fontWeight: 'bold' }}>Anti-Fraud Scan (20%)</Typography>
                    <Box component="div" sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
                      <Typography variant="body2">Trust rating: {appDetail.loan.verification_matrix?.fraud?.score}/100</Typography>
                      <Typography variant="body2" sx={{ color: appDetail.loan.verification_matrix?.fraud?.passed ? '#10b981' : '#f43f5e' }}>
                        {appDetail.loan.verification_matrix?.fraud?.passed ? 'SAFE' : 'FRAUD_ALERT'}
                      </Typography>
                    </Box>
                  </Paper>

                  {/* Row 3 */}
                  <Paper variant="outlined" sx={{ p: 2, bgcolor: 'transparent', borderColor: 'rgba(255,255,255,0.05)' }}>
                    <Typography variant="subtitle2" sx={{ color: 'var(--text-secondary)', fontWeight: 'bold' }}>Credit Bureau CIBIL (15%)</Typography>
                    <Box component="div" sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
                      <Typography variant="body2">CIBIL score: {appDetail.loan.verification_matrix?.bureau?.cibilScore}</Typography>
                      <Typography variant="body2" sx={{ color: appDetail.loan.verification_matrix?.bureau?.passed ? '#10b981' : '#f43f5e' }}>
                        {appDetail.loan.verification_matrix?.bureau?.passed ? 'ACCEPTABLE' : 'UNACCEPTABLE'}
                      </Typography>
                    </Box>
                  </Paper>

                  <Paper variant="outlined" sx={{ p: 2, bgcolor: 'transparent', borderColor: 'rgba(255,255,255,0.05)' }}>
                    <Typography variant="subtitle2" sx={{ color: 'var(--text-secondary)', fontWeight: 'bold' }}>DTI Affordability (10%)</Typography>
                    <Box component="div" sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
                      <Typography variant="body2">DTI ratio: {appDetail.loan.verification_matrix?.affordability?.dtiRatio}%</Typography>
                      <Typography variant="body2" sx={{ color: appDetail.loan.verification_matrix?.affordability?.dtiRatio > 50 ? '#f43f5e' : '#10b981' }}>
                        {appDetail.loan.verification_matrix?.affordability?.dtiRatio > 50 ? 'HIGH_DEBT_RISK' : 'HEALTHY'}
                      </Typography>
                    </Box>
                  </Paper>
                </div>

                {/* --- Section 4: Extracted Documents & Classification --- */}
                <Typography variant="h6" className="gradient-text" sx={{ fontWeight: 'bold', mb: 2 }}>Uploaded Documents (Encrypted-at-Rest)</Typography>
                
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '32px' }}>
                  {appDetail.documents?.map((doc) => (
                    <Paper key={doc.id} variant="outlined" sx={{ p: 2, textAlign: 'center', bgcolor: 'transparent', borderColor: 'rgba(255,255,255,0.05)' }}>
                      <Typography variant="caption" sx={{ display: 'block', fontWeight: 'bold', mb: 0.5 }}>{doc.document_type.toUpperCase()}</Typography>
                      
                      {doc.document_type === 'liveness_video' ? (
                        <Box component="div" sx={{ mt: 1 }}>
                          <video 
                            src={`${backendUrl}/api/documents/${doc.id}?token=${token}`} 
                            controls 
                            playsInline
                            style={{ width: '100%', maxHeight: '140px', borderRadius: '4px', background: '#000' }} 
                          />
                        </Box>
                      ) : (
                        <>
                          <Typography variant="caption" sx={{ color: 'var(--text-muted)', display: 'block', mb: 1 }}>Conf: {doc.classification_confidence}%</Typography>
                          <Box component="div" sx={{ mt: 1, display: 'flex', gap: 1, justifyContent: 'center' }}>
                            <Button
                              variant="outlined"
                              size="small"
                              onClick={() => handlePreview(doc.id, doc.document_type)}
                              startIcon={<Visibility />}
                              sx={{ textTransform: 'none', fontSize: 10 }}
                            >
                              Preview
                            </Button>
                            <Button
                              variant="outlined"
                              size="small"
                              href={`${backendUrl}/api/documents/${doc.id}?token=${token}`}
                              target="_blank"
                              startIcon={<OpenInNew />}
                              sx={{ textTransform: 'none', fontSize: 10 }}
                            >
                              Open
                            </Button>
                          </Box>
                        </>
                      )}
                    </Paper>
                  ))}
                </div>

                {/* --- Section 4.5: Document Fraud Reports --- */}
                {appDetail.loan.verification_matrix?.documentFraudReports && (
                  <>
                    <Typography variant="h6" className="gradient-text" sx={{ fontWeight: 'bold', mb: 2 }}>AI Document Authenticity & Fraud Reports</Typography>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '32px' }}>
                      {appDetail.loan.verification_matrix.documentFraudReports.map((report: any, idx: number) => {
                        const recColor = report.recommendation === 'APPROVE' ? '#10b981' : report.recommendation === 'REJECT' ? '#f43f5e' : '#f59e0b';
                        return (
                          <Paper key={idx} variant="outlined" sx={{ p: 2, bgcolor: 'rgba(255,255,255,0.01)', borderColor: 'rgba(255,255,255,0.05)' }}>
                            <Box component="div" sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                              <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                                {report.documentType.toUpperCase()} REPORT
                              </Typography>
                              <Box component="div" sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                                <Typography variant="caption" sx={{ color: 'var(--text-secondary)' }}>Trust Score: {report.confidenceScore}%</Typography>
                                <Box
                                  component="span"
                                  sx={{
                                    px: 1, py: 0.2, borderRadius: 5, fontSize: 10, fontWeight: 'bold',
                                    bgcolor: `${recColor}1e`, color: recColor
                                  }}
                                >
                                  {report.recommendation}
                                </Box>
                              </Box>
                            </Box>

                            <Divider sx={{ my: 1, borderColor: 'rgba(255,255,255,0.05)' }} />

                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '12px', marginTop: '8px' }}>
                              <Typography variant="caption" sx={{ color: report.tamperingDetected ? '#f43f5e' : '#10b981', display: 'block' }}>
                                • Tampering Detected: {report.tamperingDetected ? 'YES' : 'NO'}
                              </Typography>
                              <Typography variant="caption" sx={{ color: 'var(--text-secondary)', display: 'block' }}>
                                • Risk Level: {report.riskLevel}
                              </Typography>
                              <Typography variant="caption" sx={{ color: report.securityFeatureStatus.logoPresent ? '#10b981' : '#f43f5e', display: 'block' }}>
                                • Expected Logos: {report.securityFeatureStatus.logoPresent ? 'FOUND' : 'MISSING'}
                              </Typography>
                            </div>

                            {/* Observations list */}
                            {report.observations?.length > 0 && (
                              <Box component="div" sx={{ mt: 1.5 }}>
                                <Typography variant="caption" sx={{ fontWeight: 'bold', color: 'var(--text-secondary)', display: 'block', mb: 0.5 }}>Observations:</Typography>
                                {report.observations.map((obs: string, i: number) => (
                                  <Typography key={i} variant="caption" sx={{ display: 'block', color: obs.includes('CRITICAL') ? '#f43f5e' : 'var(--text-muted)' }}>
                                    - {obs}
                                  </Typography>
                                ))}
                              </Box>
                            )}

                            {/* Suspected Edits list */}
                            {report.suspectedEdits?.length > 0 && (
                              <Box component="div" sx={{ mt: 1.5, p: 1, bgcolor: 'rgba(244,63,94,0.05)', borderRadius: '4px', border: '1px solid rgba(244,63,94,0.1)' }}>
                                <Typography variant="caption" sx={{ fontWeight: 'bold', color: '#f43f5e', display: 'block', mb: 0.5 }}>Suspected Edits / Tampering Details:</Typography>
                                {report.suspectedEdits.map((edit: any, i: number) => (
                                  <Typography key={i} variant="caption" sx={{ display: 'block', color: '#f3f4f6' }}>
                                    [Field: {edit.field}] - {edit.reason} (Confidence: {edit.confidence}%)
                                  </Typography>
                                ))}
                              </Box>
                            )}
                          </Paper>
                        );
                      })}
                    </div>
                  </>
                )}

                {/* --- Section 5: Audit Trail --- */}
                <Typography variant="h6" className="gradient-text" sx={{ fontWeight: 'bold', mb: 2 }}>Audit Trail Timeline</Typography>
                
                <List sx={{ mb: 4, bgcolor: 'rgba(255,255,255,0.01)', borderRadius: 2, p: 2 }}>
                  {appDetail.auditTrail?.map((trail) => (
                    <ListItem key={trail.id} sx={{ alignItems: 'flex-start', px: 1, py: 1 }}>
                      <ListItemIcon sx={{ minWidth: 36, mt: 0.5 }}>
                        <Schedule sx={{ color: '#6366f1', fontSize: 20 }} />
                      </ListItemIcon>
                      <ListItemText
                        primary={
                          <Typography sx={{ fontSize: 13, color: '#f3f4f6' }}>
                            {trail.description}
                          </Typography>
                        }
                        secondary={
                          <Typography sx={{ fontSize: 11, color: 'var(--text-muted)' }}>
                            {`${new Date(trail.created_at).toLocaleString()} - ${trail.actor_name || 'System AI Worker'}`}
                          </Typography>
                        }
                      />
                    </ListItem>
                  ))}
                </List>

                {/* --- Human Admin Decision Action panel --- */}
                {appDetail.loan.status === 'pending' || appDetail.loan.status === 'processing' || appDetail.loan.status === 'requested_documents' ? (
                  <Box component="div" sx={{ display: 'flex', gap: 2, mt: 3 }}>
                    <Button
                      variant="contained"
                      color="success"
                      fullWidth
                      onClick={() => { setDecisionAction('approve'); setActionModalOpen(true); }}
                      sx={{ bgcolor: '#10b981', '&:hover': { bgcolor: '#059669' }, fontWeight: 'bold', textTransform: 'none' }}
                    >
                      Approve Application
                    </Button>
                    
                    <Button
                      variant="contained"
                      color="warning"
                      fullWidth
                      onClick={() => { setDecisionAction('request-docs'); setActionModalOpen(true); }}
                      sx={{ bgcolor: '#f59e0b', '&:hover': { bgcolor: '#d97706' }, color: '#fff', fontWeight: 'bold', textTransform: 'none' }}
                    >
                      Request Docs Change
                    </Button>

                    <Button
                      variant="contained"
                      color="error"
                      fullWidth
                      onClick={() => { setDecisionAction('reject'); setActionModalOpen(true); }}
                      sx={{ bgcolor: '#f43f5e', '&:hover': { bgcolor: '#e11d48' }, fontWeight: 'bold', textTransform: 'none' }}
                    >
                      Reject Application
                    </Button>
                  </Box>
                ) : (
                  <Alert severity="success" sx={{ bgcolor: 'rgba(16, 185, 129, 0.15)', color: '#10b981' }}>
                    This application has been finalized: **{appDetail.loan.status.toUpperCase()}**
                  </Alert>
                )}

              </CardContent>
            </Card>
          </div>
        )}
      </div>
      </>
      )}

      {/* --- Action Decision dialog Overlay --- */}
      <Dialog
        open={actionModalOpen}
        onClose={() => setActionModalOpen(false)}
      >
        {/* Style wrapper inside Dialog Content to prevent strict typings issues */}
        <div style={{ background: '#1f2937', color: '#f3f4f6', minWidth: '350px', padding: '16px' }}>
          <DialogTitle sx={{ fontWeight: 'bold', p: 1 }}>
            {decisionAction === 'approve' ? 'Approve Loan Request' : decisionAction === 'reject' ? 'Reject Loan Request' : 'Request Additional Documents'}
          </DialogTitle>
          <DialogContent sx={{ p: 1, my: 1 }}>
            <Typography variant="body2" sx={{ color: 'var(--text-secondary)', mb: 2 }}>
              Please write review comments to include in the loan audit trail and reviewer logs.
            </Typography>
            <TextField
              autoFocus
              fullWidth
              multiline
              rows={3}
              label="Review Comments"
              value={comments}
              onChange={(e) => setComments(e.target.value)}
            />
          </DialogContent>
          <DialogActions sx={{ p: 1 }}>
            <Button onClick={() => setActionModalOpen(false)} sx={{ color: '#9ca3af' }}>Cancel</Button>
            <Button
              onClick={handleDecisionSubmit}
              variant="contained"
              color={decisionAction === 'approve' ? 'success' : decisionAction === 'reject' ? 'error' : 'warning'}
              sx={{ fontWeight: 'bold' }}
            >
              Submit Decision
            </Button>
          </DialogActions>
        </div>
      </Dialog>
      {/* Document Preview Dialog overlay */}
      <Dialog 
        open={!!previewUrl} 
        onClose={() => {
          if (previewUrl && previewUrl.startsWith('blob:')) {
            URL.revokeObjectURL(previewUrl);
          }
          setPreviewUrl(null);
          setPreviewType(null);
        }} 
        maxWidth="md" 
        fullWidth
      >
        <div style={{ background: '#1f2937', color: '#f3f4f6', padding: '16px' }}>
          <DialogTitle sx={{ fontWeight: 'bold', px: 1, py: 1 }}>
            {previewType ? `${previewType.toUpperCase()} Preview` : 'Document Preview'}
          </DialogTitle>
          <DialogContent sx={{ p: 1, my: 1 }}>
            {previewType === 'liveness_video' ? (
              <video 
                src={previewUrl || ''} 
                controls 
                style={{ width: '100%', maxHeight: '65vh', borderRadius: '4px', background: '#000' }} 
              />
            ) : (
              <iframe 
                src={previewUrl || ''} 
                style={{ width: '100%', height: '65vh', border: 'none', background: '#fff', borderRadius: '4px' }} 
              />
            )}
          </DialogContent>
          <DialogActions sx={{ p: 1 }}>
            <Button 
              onClick={() => {
                if (previewUrl && previewUrl.startsWith('blob:')) {
                  URL.revokeObjectURL(previewUrl);
                }
                setPreviewUrl(null);
                setPreviewType(null);
              }} 
              sx={{ color: '#9ca3af' }}
            >
              Close
            </Button>
          </DialogActions>
        </div>
      </Dialog>
    </Box>
  );
}
