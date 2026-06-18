import { useState, useEffect } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Grid,
  Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, FormControl, InputLabel, Select, MenuItem,
  Chip, List, ListItem, ListItemText, Alert, CircularProgress,
  Divider, Tab, Tabs, Switch, FormControlLabel, Checkbox, FormGroup
} from '@mui/material';
import {
  Assessment, Download, CalendarToday, Email, Info,
  TrendingUp, Security, AccountBalance, Speed, WarningAmber,
  CheckCircle, Cancel, Timeline, Public, Insights
} from '@mui/icons-material';
import axios from 'axios';

interface AnalyticsPortalProps {
  token: string;
  backendUrl: string;
  userRole?: string;
}

export default function AnalyticsPortal({ token, backendUrl, userRole = 'admin' }: AnalyticsPortalProps) {
  // Loading & Error States
  const [loading, setLoading] = useState(true);
  const [kpiData, setKpiData] = useState<any>(null);
  const [chartData, setChartData] = useState<any>(null);
  const [insights, setInsights] = useState<any[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [error, setError] = useState('');

  // Filtering Options
  const [dateRange, setDateRange] = useState('30days');
  const [riskFilter, setRiskFilter] = useState('all');
  const [channelFilter, setChannelFilter] = useState('all');
  const [regionFilter, setRegionFilter] = useState('all');

  // Report Scheduling States
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scheduleReportCategory, setScheduleReportCategory] = useState('operational');
  const [scheduleFormat, setScheduleFormat] = useState('xlsx');
  const [scheduleFrequency, setScheduleFrequency] = useState('weekly');
  const [scheduleRecipients, setScheduleRecipients] = useState('');
  const [scheduleSuccess, setScheduleSuccess] = useState('');

  // Active Tab
  const [activeTab, setActiveTab] = useState(0);

  // Fetch Data
  const fetchAnalyticsData = async () => {
    setLoading(true);
    setError('');
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const queryParams = `?dateRange=${dateRange}&risk=${riskFilter}&channel=${channelFilter}&region=${regionFilter}`;
      const [kpisRes, chartsRes, insightsRes, logsRes] = await Promise.all([
        axios.get(`${backendUrl}/api/analytics/kpis${queryParams}`, { headers }),
        axios.get(`${backendUrl}/api/analytics/visualizations${queryParams}`, { headers }),
        axios.get(`${backendUrl}/api/analytics/insights`, { headers }),
        axios.get(`${backendUrl}/api/analytics/audit-logs`, { headers })
      ]);
      setKpiData(kpisRes.data);
      setChartData(chartsRes.data);
      setInsights(insightsRes.data);
      setAuditLogs(logsRes.data);
    } catch (err: any) {
      console.error('Error fetching analytics data:', err);
      setError('Failed to load real-time analytics data. Displaying high-fidelity sandbox metrics.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalyticsData();
  }, [dateRange, riskFilter, channelFilter, regionFilter]);

  // Download Trigger
  const handleExport = (category: string, format: string) => {
    const url = `${backendUrl}/api/analytics/export?category=${category}&format=${format}`;
    // Open in a new tab or trigger native download
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `kyc_report_${category}_${Date.now()}.${format}`);
    // Attach authorization header by creating a blob if necessary, or just letting the browser request it
    // For ease of demo/use, we stream download directly or use token via query params
    const downloadUrl = `${backendUrl}/api/analytics/export?category=${category}&format=${format}&token=${token}`;
    link.href = downloadUrl;
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Submit Schedule
  const handleScheduleSubmit = async () => {
    setScheduleSuccess('');
    try {
      const emails = scheduleRecipients.split(',').map(e => e.trim()).filter(Boolean);
      await axios.post(
        `${backendUrl}/api/analytics/schedule`,
        {
          category: scheduleReportCategory,
          format: scheduleFormat,
          frequency: scheduleFrequency,
          recipients: emails
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setScheduleSuccess('Report schedule created successfully!');
      setTimeout(() => {
        setScheduleOpen(false);
        setScheduleSuccess('');
        setScheduleRecipients('');
      }, 1500);
      // Refresh audit log
      const logsRes = await axios.get(`${backendUrl}/api/analytics/audit-logs`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setAuditLogs(logsRes.data);
    } catch (err) {
      console.error('Error scheduling report:', err);
    }
  };

  // Render sparkles / mini charts for KPI cards
  const renderSparkline = (points: number[], strokeColor: string) => {
    const width = 120;
    const height = 30;
    const maxVal = Math.max(...points, 1);
    const minVal = Math.min(...points, 0);
    const range = maxVal - minVal;

    const pathD = points.map((p, i) => {
      const x = (i / (points.length - 1)) * width;
      const y = height - ((p - minVal) / range) * height;
      return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
    }).join(' ');

    return (
      <svg width={width} height={height} style={{ overflow: 'visible' }}>
        <path d={pathD} fill="none" stroke={strokeColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  };

  // Check RBAC permission for restricted downloads
  const hasComplianceAccess = ['admin', 'compliance_officer', 'executive'].includes(userRole.toLowerCase());

  if (loading && !kpiData) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
        <CircularProgress size={50} color="primary" />
      </Box>
    );
  }

  // Fallback to mock data if API call failed
  const kpis = kpiData || {
    customerOnboarding: { totalApplications: 125, applicationsToday: 8, applicationsThisWeek: 42, applicationsThisMonth: 112, growthPercentage: 14.5 },
    kycProcessing: { pendingVerification: 14, inReview: 8, approved: 89, rejected: 14, expiredApplications: 0 },
    approvalAnalytics: { approvalRatePercentage: 78.5, rejectionRatePercentage: 21.5, averageProcessingTime: '4 mins', verificationSuccessRate: 94.2 },
    fraudAnalytics: { fraudAlertsGenerated: 18, confirmedFraudCases: 6, suspiciousDocuments: 9, duplicateIdentityAttempts: 4, deviceRiskIncidents: 5 },
    revenueAnalytics: { revenueGenerated: 18850, costPerVerification: 45, roiAnalysisPercentage: 45.2 }
  };

  const charts = chartData || {
    applicationTrend: [
      { date: 'Mon', count: 12 }, { date: 'Tue', count: 15 }, { date: 'Wed', count: 10 },
      { date: 'Thu', count: 22 }, { date: 'Fri', count: 18 }, { date: 'Sat', count: 28 },
      { date: 'Sun', count: 32 }
    ],
    approvalFunnel: [
      { stage: 'Submitted', count: 125 },
      { stage: 'Doc Check', count: 112 },
      { stage: 'Identity Match', count: 98 },
      { stage: 'Risk Assessment', count: 92 },
      { stage: 'Approved', count: 89 }
    ],
    geographicAnalytics: [
      { name: 'Maharashtra', count: 48 },
      { name: 'Karnataka', count: 32 },
      { name: 'Delhi', count: 28 },
      { name: 'Telangana', count: 25 },
      { name: 'Tamil Nadu', count: 22 },
      { name: 'Uttar Pradesh', count: 18 }
    ],
    fraudAnalytics: {
      fraudTrend: [{ date: 'M', alerts: 2 }, { date: 'T', alerts: 4 }, { date: 'W', alerts: 1 }, { date: 'T', alerts: 5 }, { date: 'F', alerts: 3 }],
      typeDistribution: [
        { name: 'Identity Mismatch', value: 45 },
        { name: 'Altered Slip', value: 25 },
        { name: 'Device Risk', value: 20 },
        { name: 'Liveness Failed', value: 10 }
      ]
    }
  };

  return (
    <Box sx={{ color: '#f3f4f6' }}>
      {error && <Alert severity="warning" sx={{ mb: 3, bgcolor: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b' }}>{error}</Alert>}

      {/* FILTER CONTROLS PANEL */}
      <Card className="glass-panel" sx={{ p: 2, mb: 4, background: 'rgba(31, 41, 55, 0.45)', border: '1px solid rgba(255,255,255,0.06)' }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={3} md={2.5}>
            <FormControl size="small" fullWidth>
              <InputLabel>Date Filter</InputLabel>
              <Select value={dateRange} label="Date Filter" onChange={(e) => setDateRange(e.target.value)}>
                <MenuItem value="today">Today</MenuItem>
                <MenuItem value="7days">Last 7 Days</MenuItem>
                <MenuItem value="30days">Last 30 Days</MenuItem>
                <MenuItem value="lastyear">Last Year</MenuItem>
                <MenuItem value="all">All Time</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={3} md={2.5}>
            <FormControl size="small" fullWidth>
              <InputLabel>Risk Filter</InputLabel>
              <Select value={riskFilter} label="Risk Filter" onChange={(e) => setRiskFilter(e.target.value)}>
                <MenuItem value="all">All Risks</MenuItem>
                <MenuItem value="high">High Risk</MenuItem>
                <MenuItem value="medium">Medium Risk</MenuItem>
                <MenuItem value="low">Low Risk</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={3} md={2.5}>
            <FormControl size="small" fullWidth>
              <InputLabel>Source Channel</InputLabel>
              <Select value={channelFilter} label="Source Channel" onChange={(e) => setChannelFilter(e.target.value)}>
                <MenuItem value="all">All Channels</MenuItem>
                <MenuItem value="mobile">Mobile App</MenuItem>
                <MenuItem value="web">Web Portal</MenuItem>
                <MenuItem value="api">Rest API</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={3} md={2.5}>
            <FormControl size="small" fullWidth>
              <InputLabel>Region Branch</InputLabel>
              <Select value={regionFilter} label="Region Branch" onChange={(e) => setRegionFilter(e.target.value)}>
                <MenuItem value="all">All Regions</MenuItem>
                <MenuItem value="north">North Branch</MenuItem>
                <MenuItem value="south">South Branch</MenuItem>
                <MenuItem value="west">West Branch</MenuItem>
                <MenuItem value="east">East Branch</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} md={2} sx={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button
              variant="outlined"
              size="small"
              onClick={() => {
                setDateRange('30days');
                setRiskFilter('all');
                setChannelFilter('all');
                setRegionFilter('all');
              }}
              sx={{ textTransform: 'none', borderColor: 'rgba(255,255,255,0.15)', color: '#9ca3af' }}
            >
              Reset
            </Button>
          </Grid>
        </Grid>
      </Card>

      {/* METRICS & VIEW MODES */}
      <Tabs
        value={activeTab}
        onChange={(_, val) => setActiveTab(val)}
        sx={{
          mb: 4,
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          '& .MuiTab-root': {
            color: '#9ca3af',
            textTransform: 'none',
            fontSize: '15px',
            fontWeight: 'medium',
            '&.Mui-selected': {
              color: '#818cf8',
              fontWeight: 'bold'
            }
          }
        }}
        textColor="primary"
        indicatorColor="primary"
      >
        <Tab icon={<TrendingUp sx={{ mr: 1 }} />} iconPosition="start" label="Executive Dashboard" />
        <Tab icon={<Insights sx={{ mr: 1 }} />} iconPosition="start" label="Advanced Analytics" />
        <Tab icon={<Assessment sx={{ mr: 1 }} />} iconPosition="start" label="Report Center" />
      </Tabs>

      {/* TAB 0: EXECUTIVE DASHBOARD */}
      {activeTab === 0 && (
        <Box>
          {/* Executive metrics grids */}
          <Grid container spacing={3} sx={{ mb: 4 }}>
            {/* Customer Onboarding */}
            <Grid item xs={12} sm={6} md={3}>
              <Card className="glass-panel" sx={{ bgcolor: 'rgba(99, 102, 241, 0.05)', border: '1px solid rgba(99,102,241,0.15)' }}>
                <CardContent>
                  <Typography variant="caption" sx={{ color: '#9ca3af', textTransform: 'uppercase', letterSpacing: 1 }}>Customer Onboarding</Typography>
                  <Typography variant="h3" sx={{ fontWeight: '800', mt: 1.5, mb: 1, color: '#f3f4f6' }}>
                    {kpis.customerOnboarding.totalApplications}
                  </Typography>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Typography variant="body2" sx={{ color: '#10b981', fontWeight: 'bold' }}>
                      ▲ +{kpis.customerOnboarding.growthPercentage}%
                    </Typography>
                    {renderSparkline([20, 35, 45, 60, 85, 110, 125], '#6366f1')}
                  </Box>
                </CardContent>
              </Card>
            </Grid>

            {/* KYC Processing Rate */}
            <Grid item xs={12} sm={6} md={3}>
              <Card className="glass-panel" sx={{ bgcolor: 'rgba(16, 185, 129, 0.05)', border: '1px solid rgba(16,185,129,0.15)' }}>
                <CardContent>
                  <Typography variant="caption" sx={{ color: '#9ca3af', textTransform: 'uppercase', letterSpacing: 1 }}>Approval Rate</Typography>
                  <Typography variant="h3" sx={{ fontWeight: '800', mt: 1.5, mb: 1, color: '#10b981' }}>
                    {kpis.approvalAnalytics.approvalRatePercentage}%
                  </Typography>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Typography variant="body2" sx={{ color: '#10b981', fontWeight: 'bold' }}>
                      ▲ +2.3%
                    </Typography>
                    {renderSparkline([70, 72, 75, 74, 76, 77, 78.5], '#10b981')}
                  </Box>
                </CardContent>
              </Card>
            </Grid>

            {/* Fraud Incidents */}
            <Grid item xs={12} sm={6} md={3}>
              <Card className="glass-panel" sx={{ bgcolor: 'rgba(244, 63, 94, 0.05)', border: '1px solid rgba(244,63,94,0.15)' }}>
                <CardContent>
                  <Typography variant="caption" sx={{ color: '#9ca3af', textTransform: 'uppercase', letterSpacing: 1 }}>Fraud Rate</Typography>
                  <Typography variant="h3" sx={{ fontWeight: '800', mt: 1.5, mb: 1, color: '#f43f5e' }}>
                    {((kpis.fraudAnalytics.fraudAlertsGenerated / kpis.customerOnboarding.totalApplications) * 100).toFixed(2)}%
                  </Typography>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Typography variant="body2" sx={{ color: '#f43f5e', fontWeight: 'bold' }}>
                      ▼ -0.5%
                    </Typography>
                    {renderSparkline([22, 19, 21, 18, 15, 12, 9], '#f43f5e')}
                  </Box>
                </CardContent>
              </Card>
            </Grid>

            {/* Revenue Analytics */}
            <Grid item xs={12} sm={6} md={3}>
              <Card className="glass-panel" sx={{ bgcolor: 'rgba(6, 182, 212, 0.05)', border: '1px solid rgba(6,182,212,0.15)' }}>
                <CardContent>
                  <Typography variant="caption" sx={{ color: '#9ca3af', textTransform: 'uppercase', letterSpacing: 1 }}>Revenue Impact</Typography>
                  <Typography variant="h3" sx={{ fontWeight: '800', mt: 1.5, mb: 1, color: '#06b6d4' }}>
                    ${kpis.revenueAnalytics.revenueGenerated.toLocaleString()}
                  </Typography>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Typography variant="body2" sx={{ color: '#06b6d4', fontWeight: 'bold' }}>
                      ▲ +15.2%
                    </Typography>
                    {renderSparkline([8000, 10000, 12000, 13500, 15000, 17500, 18850], '#06b6d4')}
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          {/* DYNAMIC VISUALIZATIONS ROW */}
          <Grid container spacing={4} sx={{ mb: 4 }}>
            {/* Trend Chart (Line / Area SVG) */}
            <Grid item xs={12} md={7}>
              <Card className="glass-panel" sx={{ p: 2.5, minHeight: '350px' }}>
                <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Timeline sx={{ color: '#6366f1' }} /> Application Submission Volume Trend
                </Typography>
                {(() => {
                  const width = 600;
                  const height = 240;
                  const padding = { left: 40, right: 20, top: 20, bottom: 30 };
                  const maxVal = Math.max(...charts.applicationTrend.map((t: any) => t.count), 1);
                  
                  const points = charts.applicationTrend.map((t: any, idx: number) => {
                    const x = padding.left + (idx / (charts.applicationTrend.length - 1)) * (width - padding.left - padding.right);
                    const y = height - padding.bottom - (t.count / maxVal) * (height - padding.top - padding.bottom);
                    return { x, y, ...t };
                  });

                  let pathD = '';
                  let areaD = '';
                  if (points.length > 0) {
                    pathD = `M ${points[0].x} ${points[0].y} ` + points.slice(1).map((p: any) => `L ${p.x} ${p.y}`).join(' ');
                    areaD = pathD + ` L ${points[points.length - 1].x} ${height - padding.bottom} L ${points[0].x} ${height - padding.bottom} Z`;
                  }

                  return (
                    <Box sx={{ width: '100%', overflowX: 'auto', mt: 2 }}>
                      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ minWidth: '500px' }}>
                        <defs>
                          <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#6366f1" stopOpacity="0.4" />
                            <stop offset="100%" stopColor="#6366f1" stopOpacity="0.0" />
                          </linearGradient>
                        </defs>
                        {/* Grid Lines */}
                        {[0, 0.25, 0.5, 0.75, 1].map((ratio, i) => {
                          const y = padding.top + ratio * (height - padding.top - padding.bottom);
                          return (
                            <line key={i} x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="rgba(255,255,255,0.06)" />
                          );
                        })}
                        {/* Area */}
                        {areaD && <path d={areaD} fill="url(#areaGradient)" />}
                        {/* Line */}
                        {pathD && <path d={pathD} fill="none" stroke="#6366f1" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />}
                        {/* Points */}
                        {points.map((p: any, i: number) => (
                          <g key={i}>
                            <circle cx={p.x} cy={p.y} r="5" fill="#1f2937" stroke="#818cf8" strokeWidth="3" />
                            <text x={p.x} y={p.y - 10} textAnchor="middle" fontSize="10" fill="#fff" fontWeight="bold">{p.count}</text>
                            <text x={p.x} y={height - 10} textAnchor="middle" fontSize="10" fill="#9ca3af">{p.date}</text>
                          </g>
                        ))}
                      </svg>
                    </Box>
                  );
                })()}
              </Card>
            </Grid>

            {/* Approval Funnel Chart (SVG block chart) */}
            <Grid item xs={12} md={5}>
              <Card className="glass-panel" sx={{ p: 2.5, minHeight: '350px' }}>
                <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Speed sx={{ color: '#10b981' }} /> Conversion Funnel Analysis
                </Typography>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 3 }}>
                  {charts.approvalFunnel.map((item: any, idx: number, arr: any[]) => {
                    const pct = Math.round((item.count / arr[0].count) * 100);
                    const widthPct = Math.max(30, pct); // minimum width for visual layout
                    return (
                      <Box key={item.stage} sx={{ display: 'flex', alignItems: 'center' }}>
                        <Typography variant="body2" sx={{ width: '130px', color: '#9ca3af', fontSize: '13px' }}>{item.stage}</Typography>
                        <Box sx={{ flexGrow: 1, position: 'relative', height: '24px', bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 1.5, overflow: 'hidden' }}>
                          <Box
                            sx={{
                              width: `${widthPct}%`,
                              height: '100%',
                              bgcolor: idx === arr.length - 1 ? '#10b981' : `rgba(99, 102, 241, ${1 - idx * 0.15})`,
                              borderRadius: 1.5,
                              transition: 'width 1s ease-in-out',
                              display: 'flex',
                              alignItems: 'center',
                              px: 1.5
                            }}
                          >
                            <Typography variant="caption" sx={{ fontWeight: 'bold', color: '#fff' }}>{item.count}</Typography>
                          </Box>
                          <Typography variant="caption" sx={{ position: 'absolute', right: 10, top: 3, fontWeight: 'bold', color: '#6b7280' }}>
                            {pct}%
                          </Typography>
                        </Box>
                      </Box>
                    );
                  })}
                </Box>
              </Card>
            </Grid>
          </Grid>

          {/* GEOGRAPHIC MAP & FRAUD MATRIX PANEL */}
          <Grid container spacing={4} sx={{ mb: 4 }}>
            {/* Geographic Interactive Bubble Map */}
            <Grid item xs={12} md={6}>
              <Card className="glass-panel" sx={{ p: 2.5, minHeight: '320px' }}>
                <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Public sx={{ color: '#06b6d4' }} /> Regional KYC Density Map
                </Typography>
                
                {/* SVG Schematic layout of regional bubbles */}
                <Box sx={{ position: 'relative', height: '220px', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                  {/* Schematic Map Representation */}
                  <svg width="100%" height="200" viewBox="0 0 400 200" style={{ background: 'rgba(0,0,0,0.1)', borderRadius: '8px' }}>
                    <path d="M120 40 L180 20 L240 40 L280 80 L220 160 L180 180 L140 160 L100 100 Z" fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="2" strokeDasharray="5,5" />
                    
                    {/* Bubbles representing states */}
                    {charts.geographicAnalytics.map((state: any, idx: number) => {
                      const positions = [
                        { x: 140, y: 110 }, // Maharashtra
                        { x: 160, y: 150 }, // Karnataka
                        { x: 180, y: 140 }, // Andhra Pradesh
                        { x: 160, y: 50 },  // Delhi
                        { x: 180, y: 120 }, // Telangana
                        { x: 180, y: 165 }, // Tamil Nadu
                        { x: 200, y: 70 }   // Uttar Pradesh
                      ];
                      const pos = positions[idx] || { x: 50 + idx * 50, y: 100 };
                      const radius = Math.max(8, Math.min(22, state.count * 0.4));
                      
                      return (
                        <g key={state.name}>
                          <circle
                            cx={pos.x}
                            cy={pos.y}
                            r={radius}
                            fill="rgba(6, 182, 212, 0.25)"
                            stroke="#06b6d4"
                            strokeWidth="1.5"
                            style={{ cursor: 'pointer' }}
                          />
                          <circle
                            cx={pos.x}
                            cy={pos.y}
                            r={radius - 4}
                            fill="#06b6d4"
                            opacity="0.8"
                          />
                          <text x={pos.x} y={pos.y + radius + 12} textAnchor="middle" fontSize="9" fill="#9ca3af" fontWeight="bold">
                            {state.name} ({state.count})
                          </text>
                        </g>
                      );
                    })}
                  </svg>
                </Box>
              </Card>
            </Grid>

            {/* Fraud Distribution Panel */}
            <Grid item xs={12} md={6}>
              <Card className="glass-panel" sx={{ p: 2.5, minHeight: '320px' }}>
                <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Security sx={{ color: '#f43f5e' }} /> Fraud Type Distribution
                </Typography>
                
                <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-around', mt: 3, gap: 2 }}>
                  {/* SVG Donut Chart */}
                  <svg width="150" height="150" viewBox="0 0 36 36">
                    <circle cx="18" cy="18" r="15.915" fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="3" />
                    {(() => {
                      let cumPct = 0;
                      const colors = ['#f43f5e', '#818cf8', '#f59e0b', '#06b6d4'];
                      return charts.fraudAnalytics.typeDistribution.map((item: any, idx: number) => {
                        const val = item.value;
                        const strokeDash = `${val} 100`;
                        const strokeOffset = 100 - cumPct + 25; // 25 is to start from top
                        cumPct += val;
                        return (
                          <circle
                            key={item.name}
                            cx="18"
                            cy="18"
                            r="15.915"
                            fill="none"
                            stroke={colors[idx] || '#fff'}
                            strokeWidth="3.5"
                            strokeDasharray={strokeDash}
                            strokeDashoffset={strokeOffset}
                          />
                        );
                      });
                    })()}
                  </svg>

                  {/* Legends */}
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                    {charts.fraudAnalytics.typeDistribution.map((item: any, idx: number) => {
                      const colors = ['#f43f5e', '#818cf8', '#f59e0b', '#06b6d4'];
                      return (
                        <Box key={item.name} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Box sx={{ width: 12, height: 12, borderRadius: '50%', bgcolor: colors[idx] }} />
                          <Typography variant="caption" sx={{ color: '#9ca3af', fontWeight: 'medium' }}>
                            {item.name}: <strong>{item.value}%</strong>
                          </Typography>
                        </Box>
                      );
                    })}
                  </Box>
                </Box>
              </Card>
            </Grid>
          </Grid>
        </Box>
      )}

      {/* TAB 1: ADVANCED ANALYTICS (RISK & OPERATION BI) */}
      {activeTab === 1 && (
        <Box>
          <Grid container spacing={4} sx={{ mb: 4 }}>
            {/* Risk Distribution Profile */}
            <Grid item xs={12} md={6}>
              <Card className="glass-panel" sx={{ p: 2.5 }}>
                <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Security sx={{ color: '#f59e0b' }} /> KYC Risk Rating Profiles
                </Typography>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3.5, mt: 3 }}>
                  <Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="body2" sx={{ fontWeight: 'bold', color: '#f43f5e' }}>High Risk / Critical Verification</Typography>
                      <Typography variant="body2" sx={{ fontWeight: 'bold' }}>{kpis.kycProcessing.rejected} Applications</Typography>
                    </Box>
                    <Box sx={{ width: '100%', height: 10, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 5, overflow: 'hidden' }}>
                      <Box sx={{ width: '15%', height: '100%', bgcolor: '#f43f5e', borderRadius: 5 }} />
                    </Box>
                  </Box>

                  <Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="body2" sx={{ fontWeight: 'bold', color: '#f59e0b' }}>Medium Risk / Manual Review</Typography>
                      <Typography variant="body2" sx={{ fontWeight: 'bold' }}>{kpis.kycProcessing.inReview} Applications</Typography>
                    </Box>
                    <Box sx={{ width: '100%', height: 10, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 5, overflow: 'hidden' }}>
                      <Box sx={{ width: '25%', height: '100%', bgcolor: '#f59e0b', borderRadius: 5 }} />
                    </Box>
                  </Box>

                  <Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="body2" sx={{ fontWeight: 'bold', color: '#10b981' }}>Low Risk / Instant Approve</Typography>
                      <Typography variant="body2" sx={{ fontWeight: 'bold' }}>{kpis.kycProcessing.approved} Applications</Typography>
                    </Box>
                    <Box sx={{ width: '100%', height: 10, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 5, overflow: 'hidden' }}>
                      <Box sx={{ width: '60%', height: '100%', bgcolor: '#10b981', borderRadius: 5 }} />
                    </Box>
                  </Box>
                </Box>
              </Card>
            </Grid>

            {/* Operational Metrics (SLA compliance) */}
            <Grid item xs={12} md={6}>
              <Card className="glass-panel" sx={{ p: 2.5 }}>
                <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Speed sx={{ color: '#818cf8' }} /> SLA Compliance & Agent Productivity
                </Typography>
                
                <Grid container spacing={3} sx={{ mt: 1 }}>
                  <Grid item xs={6}>
                    <Box sx={{ border: '1px solid rgba(255,255,255,0.05)', p: 2, borderRadius: 2, textAlign: 'center', bgcolor: 'rgba(0,0,0,0.15)' }}>
                      <Typography variant="caption" sx={{ color: '#9ca3af' }}>Avg Processing Time</Typography>
                      <Typography variant="h4" sx={{ fontWeight: 'bold', mt: 1, color: '#818cf8' }}>
                        {kpis.approvalAnalytics.averageProcessingTime}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6}>
                    <Box sx={{ border: '1px solid rgba(255,255,255,0.05)', p: 2, borderRadius: 2, textAlign: 'center', bgcolor: 'rgba(0,0,0,0.15)' }}>
                      <Typography variant="caption" sx={{ color: '#9ca3af' }}>SLA Target</Typography>
                      <Typography variant="h4" sx={{ fontWeight: 'bold', mt: 1, color: '#10b981' }}>
                        &lt; 5 mins
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6}>
                    <Box sx={{ border: '1px solid rgba(255,255,255,0.05)', p: 2, borderRadius: 2, textAlign: 'center', bgcolor: 'rgba(0,0,0,0.15)' }}>
                      <Typography variant="caption" sx={{ color: '#9ca3af' }}>SLA Compliance Rate</Typography>
                      <Typography variant="h4" sx={{ fontWeight: 'bold', mt: 1, color: '#10b981' }}>
                        98.8%
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6}>
                    <Box sx={{ border: '1px solid rgba(255,255,255,0.05)', p: 2, borderRadius: 2, textAlign: 'center', bgcolor: 'rgba(0,0,0,0.15)' }}>
                      <Typography variant="caption" sx={{ color: '#9ca3af' }}>Queue Load State</Typography>
                      <Typography variant="h4" sx={{ fontWeight: 'bold', mt: 1, color: '#f59e0b' }}>
                        NORMAL
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>
              </Card>
            </Grid>
          </Grid>

          {/* AI INSIGHTS ENGINE PANEL */}
          <Card className="glass-panel" sx={{ p: 2.5, mb: 4, background: 'linear-gradient(to right, rgba(99,102,241,0.05), rgba(6,182,212,0.05))' }}>
            <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
              <Insights sx={{ color: '#818cf8' }} /> AI OnboardTrust Insights Engine
            </Typography>
            <Divider sx={{ mb: 2, borderColor: 'rgba(255,255,255,0.05)' }} />
            <List>
              {insights.map((insight) => (
                <ListItem key={insight.id} sx={{ px: 0, py: 1.5 }}>
                  <Box
                    sx={{
                      width: 10,
                      height: 10,
                      borderRadius: '50%',
                      mr: 2,
                      bgcolor: insight.type === 'positive' ? '#10b981' : insight.type === 'warning' ? '#f43f5e' : '#9ca3af'
                    }}
                  />
                  <ListItemText
                    primary={
                      <Typography variant="body1" sx={{ fontWeight: 'medium', color: '#f3f4f6' }}>
                        {insight.text}
                      </Typography>
                    }
                    secondary={
                      <Typography variant="caption" sx={{ color: '#6b7280' }}>
                        {insight.date} | AI Recommendation Engine v2.5
                      </Typography>
                    }
                  />
                </ListItem>
              ))}
            </List>
          </Card>
        </Box>
      )}

      {/* TAB 2: REPORT CENTER (DOWNLOADS & SCHEDULING) */}
      {activeTab === 2 && (
        <Box>
          <Grid container spacing={4}>
            {/* Download and Scheduling Control Panel */}
            <Grid item xs={12} md={7}>
              <Card className="glass-panel" sx={{ p: 2.5, minHeight: '380px' }}>
                <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 3 }}>Available Reports Repository</Typography>
                
                {/* Reports Listing */}
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
                  {/* Category: Executive Summary */}
                  <Box sx={{ p: 2, border: '1px solid rgba(255,255,255,0.05)', borderRadius: 2, display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 2, bgcolor: 'rgba(0,0,0,0.1)' }}>
                    <Box>
                      <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>Executive Summary Business Report</Typography>
                      <Typography variant="caption" sx={{ color: '#9ca3af' }}>Consolidated high-level metrics for CEO/Management team</Typography>
                    </Box>
                    <Box sx={{ display: 'flex', gap: 1 }}>
                      <Button variant="outlined" size="small" startIcon={<Download />} onClick={() => handleExport('executive_summary', 'xlsx')} sx={{ textTransform: 'none' }}>Excel</Button>
                      <Button variant="outlined" size="small" startIcon={<Download />} onClick={() => handleExport('executive_summary', 'pdf')} sx={{ textTransform: 'none' }}>PDF</Button>
                      <Button variant="outlined" size="small" startIcon={<Download />} onClick={() => handleExport('executive_summary', 'csv')} sx={{ textTransform: 'none' }}>CSV</Button>
                    </Box>
                  </Box>

                  {/* Category: KYC Compliance Report */}
                  <Box sx={{ p: 2, border: '1px solid rgba(255,255,255,0.05)', borderRadius: 2, display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 2, bgcolor: 'rgba(0,0,0,0.1)' }}>
                    <Box>
                      <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>Compliance & Audit Verification Logs</Typography>
                      <Typography variant="caption" sx={{ color: '#9ca3af' }}>Detailed audit trail containing user, role, and AML status logs</Typography>
                    </Box>
                    <Box sx={{ display: 'flex', gap: 1 }}>
                      <Button variant="outlined" size="small" startIcon={<Download />} disabled={!hasComplianceAccess} onClick={() => handleExport('compliance', 'xlsx')} sx={{ textTransform: 'none' }}>Excel</Button>
                      <Button variant="outlined" size="small" startIcon={<Download />} disabled={!hasComplianceAccess} onClick={() => handleExport('compliance', 'pdf')} sx={{ textTransform: 'none' }}>PDF</Button>
                      {!hasComplianceAccess && <Chip label="RBAC Restricted" size="small" color="error" variant="outlined" />}
                    </Box>
                  </Box>

                  {/* Category: Fraud Investigation */}
                  <Box sx={{ p: 2, border: '1px solid rgba(255,255,255,0.05)', borderRadius: 2, display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 2, bgcolor: 'rgba(0,0,0,0.1)' }}>
                    <Box>
                      <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>Fraud Trend Investigation Report</Typography>
                      <Typography variant="caption" sx={{ color: '#9ca3af' }}>List of suspicious documents, duplicate IDs and risk scores</Typography>
                    </Box>
                    <Box sx={{ display: 'flex', gap: 1 }}>
                      <Button variant="outlined" size="small" startIcon={<Download />} onClick={() => handleExport('fraud', 'xlsx')} sx={{ textTransform: 'none' }}>Excel</Button>
                      <Button variant="outlined" size="small" startIcon={<Download />} onClick={() => handleExport('fraud', 'json')} sx={{ textTransform: 'none' }}>JSON</Button>
                    </Box>
                  </Box>
                </Box>

                <Button
                  variant="contained"
                  color="primary"
                  startIcon={<Email />}
                  onClick={() => setScheduleOpen(true)}
                  sx={{ mt: 4, textTransform: 'none', fontWeight: 'bold', bgcolor: '#818cf8', '&:hover': { bgcolor: '#6366f1' } }}
                >
                  Schedule Automated Delivery
                </Button>
              </Card>
            </Grid>

            {/* Audit Logs Trail Panel */}
            <Grid item xs={12} md={5}>
              <Card className="glass-panel" sx={{ p: 2.5, minHeight: '380px' }}>
                <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 3 }}>Reporting Module Audit Trail</Typography>
                
                <Box sx={{ maxHeight: '280px', overflowY: 'auto', pr: 1 }}>
                  {auditLogs.map((log: any) => (
                    <Box key={log.id} sx={{ mb: 2, p: 1.5, borderLeft: '3px solid #818cf8', bgcolor: 'rgba(255,255,255,0.02)', borderRadius: '0 8px 8px 0' }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                        <Typography variant="caption" sx={{ color: '#818cf8', fontWeight: 'bold' }}>
                          {log.action}
                        </Typography>
                        <Typography variant="caption" sx={{ color: '#6b7280' }}>
                          {new Date(log.created_at).toLocaleTimeString()}
                        </Typography>
                      </Box>
                      <Typography variant="body2" sx={{ color: '#e5e7eb', fontSize: 13 }}>
                        {log.description}
                      </Typography>
                      <Typography variant="caption" sx={{ color: '#6b7280', display: 'block', mt: 0.5 }}>
                        Actor: {log.actor_name || 'Admin User'}
                      </Typography>
                    </Box>
                  ))}
                  {auditLogs.length === 0 && (
                    <Typography variant="body2" sx={{ color: '#9ca3af', textAlign: 'center', py: 4 }}>No audit logs logged in current session.</Typography>
                  )}
                </Box>
              </Card>
            </Grid>
          </Grid>
        </Box>
      )}

      {/* REPORT SCHEDULING DIALOG */}
      <Dialog open={scheduleOpen} onClose={() => setScheduleOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 'bold', bgcolor: '#1f2937', color: '#fff' }}>
          Schedule Automated Report Delivery
        </DialogTitle>
        <DialogContent sx={{ bgcolor: '#1f2937', color: '#fff', pt: 2 }}>
          {scheduleSuccess && <Alert severity="success" sx={{ mb: 2 }}>{scheduleSuccess}</Alert>}
          <Grid container spacing={3} sx={{ mt: 0.5 }}>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth size="small">
                <InputLabel>Report Category</InputLabel>
                <Select value={scheduleReportCategory} label="Report Category" onChange={(e) => setScheduleReportCategory(e.target.value)}>
                  <MenuItem value="executive_summary">Executive Summary</MenuItem>
                  <MenuItem value="compliance">KYC Compliance Audit</MenuItem>
                  <MenuItem value="fraud">Fraud Trend Analysis</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth size="small">
                <InputLabel>Format</InputLabel>
                <Select value={scheduleFormat} label="Format" onChange={(e) => setScheduleFormat(e.target.value)}>
                  <MenuItem value="xlsx">Excel Workbook (.xlsx)</MenuItem>
                  <MenuItem value="pdf">PDF Document (.pdf)</MenuItem>
                  <MenuItem value="csv">CSV Sheet (.csv)</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={12}>
              <FormControl fullWidth size="small">
                <InputLabel>Frequency</InputLabel>
                <Select value={scheduleFrequency} label="Frequency" onChange={(e) => setScheduleFrequency(e.target.value)}>
                  <MenuItem value="daily">Daily Onboard Recap</MenuItem>
                  <MenuItem value="weekly">Weekly Operational Summary</MenuItem>
                  <MenuItem value="monthly">Monthly Regulatory Compliance Audit</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <TextField
                label="Recipients Emails (comma separated)"
                placeholder="compliance@company.com, risk-ops@company.com"
                fullWidth
                size="small"
                value={scheduleRecipients}
                onChange={(e) => setScheduleRecipients(e.target.value)}
                required
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions sx={{ bgcolor: '#1f2937', px: 3, pb: 3 }}>
          <Button onClick={() => setScheduleOpen(false)} sx={{ color: '#9ca3af' }}>Cancel</Button>
          <Button variant="contained" onClick={handleScheduleSubmit} disabled={!scheduleRecipients} sx={{ bgcolor: '#818cf8', '&:hover': { bgcolor: '#6366f1' } }}>
            Confirm Schedule
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
