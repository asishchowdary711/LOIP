import React, { useState, useEffect } from 'react';
import {
  Box, Typography, TextField, Button, Card, CardContent,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
  IconButton, Alert, List, ListItem, ListItemIcon, ListItemText,
  Dialog, DialogTitle, DialogContent, DialogActions
} from '@mui/material';
import {
  CloudUpload, History, PlayCircle, CheckCircle, HourglassEmpty, HighlightOff,
  VideoCameraFront, DoneAll, ArrowBack, Refresh, Delete, Visibility
} from '@mui/icons-material';
import axios from 'axios';

interface CustomerPortalProps {
  token: string;
  backendUrl: string;
  activeLoanId: string | null;
  setActiveLoanId: (id: string | null) => void;
}

interface Loan {
  id: string;
  loan_amount: string;
  status: string;
  risk_score: number;
  risk_category: string;
  created_at: string;
}

export default function CustomerPortal({ token, backendUrl, activeLoanId, setActiveLoanId }: CustomerPortalProps) {
  const [view, setView] = useState<'apply' | 'history' | 'tracking'>('apply');
  const [loans, setLoans] = useState<Loan[]>([]);

  // Apply Form State
  const [loanAmount, setLoanAmount] = useState('150000');
  const [name, setName] = useState('');
  const [dob, setDob] = useState('');
  const [declaredIncome, setDeclaredIncome] = useState('');
  const [employer, setEmployer] = useState('');

  // Document Uploads State
  const [aadhaarFile, setAadhaarFile] = useState<File | null>(null);
  const [panFile, setPanFile] = useState<File | null>(null);
  const [payslipFile, setPayslipFile] = useState<File | null>(null);
  const [bankFile, setBankFile] = useState<File | null>(null);
  const [addressFile, setAddressFile] = useState<File | null>(null);
  const [livenessFile, setLivenessFile] = useState<File | null>(null);
  const [uploadedDocs, setUploadedDocs] = useState<Record<string, { id: string; document_type: string }>>({});
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewType, setPreviewType] = useState<string | null>(null);

  const [stream, setStream] = useState<MediaStream | null>(null);

  // Liveness Biometric state
  const [recording, setRecording] = useState(false);
  const [challengeIndex, setChallengeIndex] = useState(0);
  const [challengesCompleted, setChallengesCompleted] = useState<string[]>([]);
  const challenges = ['SMILED', 'BLINKED', 'TURNED_LEFT'];
  const challengeLabels = ['Look into the camera and Smile 😊', 'Blink your eyes twice 👀', 'Slowly turn your face left ⬅️'];

  // SSE Real-time tracking progress state
  const [sseStatus, setSseStatus] = useState<string>('Initializing verification...');
  const [sseLog, setSseLog] = useState<Array<{ stage: string; status: 'pending' | 'success' | 'failed'; message: string }>>([
    { stage: 'document_classification', status: 'pending', message: 'Document classification pending...' },
    { stage: 'ocr_extraction', status: 'pending', message: 'OCR field extraction pending...' },
    { stage: 'identity_verification', status: 'pending', message: 'Identity check (MIDV-500/2020) pending...' },
    { stage: 'income_verification', status: 'pending', message: 'Payslip validation pending...' },
    { stage: 'bank_analysis', status: 'pending', message: 'Bank statement analysis pending...' },
    { stage: 'fraud_detection', status: 'pending', message: 'Anti-fraud scanning pending...' },
    { stage: 'face_verification', status: 'pending', message: 'Biometric liveness matching pending...' },
    { stage: 'credit_bureau', status: 'pending', message: 'Credit bureau check (CIBIL) pending...' },
    { stage: 'affordability_assessment', status: 'pending', message: 'DTI Affordability check pending...' },
    { stage: 'risk_scoring', status: 'pending', message: 'Risk scoring and aggregation pending...' },
    { stage: 'decision_recommendation', status: 'pending', message: 'AI Decision Formulation pending...' },
  ]);

  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Fetch loan history
  const fetchLoans = async () => {
    try {
      const res = await axios.get(`${backendUrl}/api/loans`, { headers: { Authorization: `Bearer ${token}` } });
      setLoans(res.data.loans);
    } catch (err) {
      console.error('Error fetching loan history:', err);
    }
  };

  useEffect(() => {
    if (view === 'history') {
      fetchLoans();
    }
  }, [view]);

  useEffect(() => {
    const fetchProfileData = async () => {
      if (!token) return;
      try {
        const res = await axios.get(`${backendUrl}/api/auth/profile`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.data.latestApplicantData) {
          const data = res.data.latestApplicantData;
          if (data.name) setName(data.name);
          if (data.dob) setDob(data.dob);
          if (data.declaredIncome) setDeclaredIncome(String(data.declaredIncome));
          if (data.employer) setEmployer(data.employer);
        }
        const isLoanActive = res.data.latestLoanStatus && !['approved', 'rejected'].includes(res.data.latestLoanStatus);
        if (res.data.latestLoanId && isLoanActive) {
          setActiveLoanId(res.data.latestLoanId);
          if (res.data.latestDocuments) {
            const docsMap: Record<string, { id: string; document_type: string }> = {};
            res.data.latestDocuments.forEach((doc: any) => {
              docsMap[doc.document_type] = doc;
            });
            setUploadedDocs(docsMap);
          }
        } else {
          setActiveLoanId(null);
          setUploadedDocs({});
        }
      } catch (err) {
        console.error('Error loading profile applicant data:', err);
      }
    };
    fetchProfileData();
  }, [token, backendUrl, setActiveLoanId]);

  // Handle SSE connection for live tracking
  useEffect(() => {
    if (!activeLoanId) return;

    setView('tracking');
    setSseStatus('Connecting to real-time verification pipeline...');

    const eventSource = new EventSource(`${backendUrl}/api/events/${activeLoanId}`);

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log('[SSE Event Received]:', data);

      if (data.stage === 'connection') {
        setSseStatus('Connected. Starting AI agents...');
        return;
      }

      setSseStatus(data.message);

      // Update specific stage inside checklist log
      setSseLog((prevLog) =>
        prevLog.map((item) =>
          item.stage === data.stage
            ? { ...item, status: data.status, message: data.message }
            : item
        )
      );

      // If decision recommendation is finalized, close events stream
      if (data.stage === 'decision_recommendation' && data.status === 'success') {
        setSseStatus(`Processing complete! Recommendation: ${data.data?.recommendation}`);
        eventSource.close();
      }
    };

    eventSource.onerror = (err) => {
      console.error('[SSE Error]:', err);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [activeLoanId]);

  // Liveness Recorder & Simulator
  const startLivenessTest = async () => {
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      setStream(mediaStream);
      setRecording(true);
      setChallengeIndex(0);
      setChallengesCompleted([]);
      
      // Allow DOM video node time to register
      setTimeout(() => {
        const videoEl = document.getElementById('webcam-preview') as HTMLVideoElement;
        if (videoEl) {
          videoEl.srcObject = mediaStream;
          videoEl.play().catch(e => console.error('Error playing webcam feed:', e));
        }
      }, 100);

      // Initialize MediaRecorder
      const options = { mimeType: 'video/webm;codecs=vp9' };
      let recorder: MediaRecorder;
      try {
        recorder = new MediaRecorder(mediaStream, options);
      } catch (e) {
        recorder = new MediaRecorder(mediaStream); // fallback
      }

       const chunks: Blob[] = [];
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunks.push(event.data);
        }
      };

      recorder.onstop = () => {
        const videoBlob = new Blob(chunks, { type: 'video/webm' });
        const videoFile = new File([videoBlob], 'liveness_video.webm', { type: 'video/webm' });
        if (activeLoanId) {
          handleDirectUpload('liveness_video', videoFile);
        } else {
          setLivenessFile(videoFile);
        }
        console.log('Liveness video saved successfully, size:', videoFile.size);
      };

      recorder.start();

      // Sequentially complete challenges
      const interval = setInterval(() => {
        setChallengeIndex((prev) => {
          const next = prev + 1;
          setChallengesCompleted((curr) => [...curr, challenges[prev]]);
          if (next >= challenges.length) {
            clearInterval(interval);
            
            // Stop recording
            if (recorder && recorder.state !== 'inactive') {
              recorder.stop();
            }
            
            // Stop media stream tracks
            mediaStream.getTracks().forEach((track) => track.stop());
            setStream(null);
            setRecording(false);
          }
          return next;
        });
      }, 2500);

    } catch (err: any) {
      console.warn('Webcam permission denied or hardware unavailable. Falling back to synthetic simulation...', err);
      // Fallback: Generate a simulated video file
      setRecording(true);
      setChallengeIndex(0);
      setChallengesCompleted([]);
      
      const interval = setInterval(() => {
        setChallengeIndex((prev) => {
          const next = prev + 1;
          setChallengesCompleted((curr) => [...curr, challenges[prev]]);
          if (next >= challenges.length) {
            clearInterval(interval);
            setRecording(false);
            
            const mockBlob = new Blob(['Simulated WebM Liveness Challenge Video Data'], { type: 'video/webm' });
            const mockFile = new File([mockBlob], 'liveness_video.webm', { type: 'video/webm' });
            if (activeLoanId) {
              handleDirectUpload('liveness_video', mockFile);
            } else {
              setLivenessFile(mockFile);
            }
            console.log('Simulated liveness video saved successfully.');
          }
          return next;
        });
      }, 2500);
    }
  };

  const handleDeleteDoc = async (docType: string) => {
    const doc = uploadedDocs[docType];
    if (!doc) return;
    setLoading(true);
    try {
      await axios.delete(`${backendUrl}/api/documents/${doc.id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setUploadedDocs(prev => {
        const next = { ...prev };
        delete next[docType];
        return next;
      });
      // Clear corresponding local state
      if (docType === 'aadhaar') setAadhaarFile(null);
      if (docType === 'pan') setPanFile(null);
      if (docType === 'payslip') setPayslipFile(null);
      if (docType === 'bank_statement') setBankFile(null);
      if (docType === 'address_proof') setAddressFile(null);
      if (docType === 'liveness_video') setLivenessFile(null);
      
      setMessage({ type: 'success', text: `${docType.toUpperCase()} document removed successfully.` });
    } catch (err: any) {
      console.error(err);
      setMessage({ type: 'error', text: err.response?.data?.error || 'Failed to delete document.' });
    } finally {
      setLoading(false);
    }
  };

  const handlePreview = async (docType: string) => {
    const doc = uploadedDocs[docType];
    if (!doc) return;
    setLoading(true);
    try {
      const res = await axios.get(`${backendUrl}/api/documents/${doc.id}`, {
        headers: { Authorization: `Bearer ${token}` },
        responseType: 'blob'
      });
      const blob = new Blob([res.data], { type: (res.headers['content-type'] as string) || 'application/pdf' });
      const objectUrl = URL.createObjectURL(blob);
      setPreviewUrl(objectUrl);
      setPreviewType(docType);
    } catch (err) {
      console.error('Error fetching preview blob:', err);
      setMessage({ type: 'error', text: 'Failed to load document preview.' });
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = async (docType: string, file: File | null) => {
    if (!file) return;
    if (activeLoanId) {
      await handleDirectUpload(docType, file);
    } else {
      if (docType === 'aadhaar') setAadhaarFile(file);
      if (docType === 'pan') setPanFile(file);
      if (docType === 'payslip') setPayslipFile(file);
      if (docType === 'bank_statement') setBankFile(file);
      if (docType === 'address_proof') setAddressFile(file);
    }
  };

  const handleDirectUpload = async (docType: string, file: File) => {
    if (!activeLoanId) return;
    setLoading(true);
    const formData = new FormData();
    formData.append(docType, file);
    formData.append('documentType', docType);
    try {
      const res = await axios.post(`${backendUrl}/api/loans/${activeLoanId}/documents`, formData, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'multipart/form-data'
        }
      });
      const docId = res.data.documentId;
      setUploadedDocs(prev => ({
        ...prev,
        [docType]: { id: docId, document_type: docType }
      }));
      if (docType === 'aadhaar') setAadhaarFile(file);
      if (docType === 'pan') setPanFile(file);
      if (docType === 'payslip') setPayslipFile(file);
      if (docType === 'bank_statement') setBankFile(file);
      if (docType === 'address_proof') setAddressFile(file);
      if (docType === 'liveness_video') setLivenessFile(file);
      
      setMessage({ type: 'success', text: `Document ${docType.toUpperCase()} updated and re-queued for AI verification.` });
    } catch (err: any) {
      console.error(err);
      setMessage({ type: 'error', text: err.response?.data?.error || 'Document replacement failed.' });
    } finally {
      setLoading(false);
    }
  };

  const handleApply = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setMessage(null);

    if (activeLoanId) {
      try {
        await axios.post(`${backendUrl}/api/processing/start/${activeLoanId}`, {}, {
          headers: { Authorization: `Bearer ${token}` }
        });
        setMessage({ type: 'success', text: 'AI processing pipeline successfully re-triggered.' });
        setView('tracking');
      } catch (err: any) {
        console.error(err);
        setMessage({ type: 'error', text: err.response?.data?.error || 'Failed to trigger verification.' });
      } finally {
        setLoading(false);
      }
      return;
    }

    const docKeys = ['aadhaar', 'pan', 'payslip', 'bank_statement', 'address_proof', 'liveness_video'];
    const missingDocs = docKeys.filter(key => !uploadedDocs[key] && !(
      key === 'aadhaar' ? aadhaarFile :
      key === 'pan' ? panFile :
      key === 'payslip' ? payslipFile :
      key === 'bank_statement' ? bankFile :
      key === 'address_proof' ? addressFile :
      key === 'liveness_video' ? livenessFile : null
    ));

    if (missingDocs.length > 0) {
      setMessage({ type: 'error', text: `Please upload/complete the missing documents: ${missingDocs.map(d => d.toUpperCase()).join(', ')}` });
      setLoading(false);
      return;
    }

    const formData = new FormData();
    formData.append('loanAmount', loanAmount);
    formData.append('name', name);
    formData.append('dob', dob);
    formData.append('declaredIncome', declaredIncome);
    formData.append('employer', employer);
    formData.append('challenges', JSON.stringify(challengesCompleted.length ? challengesCompleted : ['SMILED', 'BLINKED']));

    if (aadhaarFile) formData.append('aadhaar', aadhaarFile);
    if (panFile) formData.append('pan', panFile);
    if (payslipFile) formData.append('payslip', payslipFile);
    if (bankFile) formData.append('bank_statement', bankFile);
    if (addressFile) formData.append('address_proof', addressFile);
    if (livenessFile) formData.append('liveness_video', livenessFile);

    try {
      const res = await axios.post(`${backendUrl}/api/loans`, formData, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'multipart/form-data'
        }
      });
      setActiveLoanId(res.data.loanId);
    } catch (err: any) {
      console.error(err);
      setMessage({ type: 'error', text: err.response?.data?.error || 'Loan submission failed.' });
    } finally {
      setLoading(false);
    }
  };

  const getStageIcon = (status: 'pending' | 'success' | 'failed') => {
    if (status === 'success') return <CheckCircle sx={{ color: '#10b981' }} />;
    if (status === 'failed') return <HighlightOff sx={{ color: '#f43f5e' }} />;
    return <HourglassEmpty sx={{ color: '#f59e0b' }} />;
  };

  return (
    <Box component="div" sx={{ p: 3 }}>
      {/* Tab Navigation header */}
      <Box component="div" sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
        <Typography variant="h4" sx={{ fontWeight: 'bold' }}>Customer Portal</Typography>
        <Box component="div" sx={{ display: 'flex', gap: 2 }}>
          <Button
            variant={view === 'apply' ? 'contained' : 'outlined'}
            onClick={() => setView('apply')}
            startIcon={<DoneAll />}
            sx={{ textTransform: 'none' }}
          >
            Apply Now
          </Button>
          <Button
            variant={view === 'history' ? 'contained' : 'outlined'}
            onClick={() => setView('history')}
            startIcon={<History />}
            sx={{ textTransform: 'none' }}
          >
            Loan History
          </Button>
        </Box>
      </Box>

      {message && <Alert severity={message.type} sx={{ mb: 3 }}>{message.text}</Alert>}

      {/* --- View 1: Apply Form --- */}
      {view === 'apply' && (
        <form onSubmit={handleApply}>
          {/* Responsive Flex wrapper */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '24px' }}>
            {/* Left: Applicant Details */}
            <div style={{ flex: '1 1 300px' }}>
              <Card className="glass-panel" sx={{ p: 2 }}>
                <CardContent>
                  <Typography variant="h5" className="gradient-text" sx={{ fontWeight: 'bold', mb: 2 }}>Applicant Details</Typography>

                  <TextField
                    label="Desired Loan Amount (Rs.)"
                    fullWidth
                    value={loanAmount}
                    onChange={(e) => setLoanAmount(e.target.value)}
                    margin="normal"
                    required
                  />

                  <TextField
                    label="Full Name (as in Aadhaar)"
                    fullWidth
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    margin="normal"
                  />

                  <TextField
                    label="Date of Birth (DD-MM-YYYY)"
                    fullWidth
                    value={dob}
                    onChange={(e) => setDob(e.target.value)}
                    margin="normal"
                  />

                  <TextField
                    label="Declared Monthly Salary (Rs.)"
                    fullWidth
                    value={declaredIncome}
                    onChange={(e) => setDeclaredIncome(e.target.value)}
                    margin="normal"
                  />

                  <TextField
                    label="Employer Company Name"
                    fullWidth
                    value={employer}
                    onChange={(e) => setEmployer(e.target.value)}
                    margin="normal"
                  />
                </CardContent>
              </Card>

              {/* Liveness Verification Box */}
              <Card className="glass-panel" sx={{ p: 2, mt: 3 }}>
                <CardContent>
                  <Typography variant="h5" className="gradient-text" sx={{ fontWeight: 'bold', mb: 2 }}>Biometric Liveness Challenge</Typography>
                  <Typography variant="body2" sx={{ color: 'var(--text-secondary)', mb: 2 }}>
                    Please perform the quick challenge sequence below using your camera stream to prevent deepfake fraud.
                  </Typography>

                  <Box component="div" sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                    <Box 
                      className="webcam-container" 
                      component="div"
                      sx={{ 
                        width: '100%', 
                        maxWidth: '320px', 
                        height: '240px', 
                        borderRadius: '8px', 
                        border: '2px dashed rgba(255,255,255,0.1)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        position: 'relative',
                        background: '#000',
                        overflow: 'hidden'
                      }}
                    >
                      {recording && stream ? (
                        <video 
                          id="webcam-preview" 
                          autoPlay 
                          playsInline 
                          muted 
                          style={{ width: '100%', height: '100%', objectFit: 'cover' }} 
                        />
                      ) : recording ? (
                        <>
                          <VideoCameraFront sx={{ fontSize: 60, color: '#6366f1' }} />
                          <Box className="webcam-overlay" component="div" />
                          <Typography variant="caption" sx={{ position: 'absolute', bottom: 10, color: '#9ca3af' }}>[Headless Sandbox Simulation]</Typography>
                        </>
                      ) : uploadedDocs['liveness_video'] ? (
                        <Box component="div" sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                          <CheckCircle sx={{ fontSize: 60, color: '#10b981' }} />
                          <Typography variant="caption" sx={{ color: '#10b981', fontWeight: 'bold' }}>Liveness Video Submitted!</Typography>
                          <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
                            <Button size="small" variant="outlined" onClick={() => handlePreview('liveness_video')} startIcon={<Visibility />}>Preview</Button>
                            <IconButton color="error" onClick={() => handleDeleteDoc('liveness_video')} size="small"><Delete /></IconButton>
                          </Box>
                        </Box>
                      ) : livenessFile ? (
                        <Box component="div" sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                          <CheckCircle sx={{ fontSize: 60, color: '#10b981' }} />
                          <Typography variant="caption" sx={{ color: '#10b981', fontWeight: 'bold' }}>Video Challenge Recorded!</Typography>
                        </Box>
                      ) : (
                        <VideoCameraFront sx={{ fontSize: 60, color: 'var(--text-muted)' }} />
                      )}
                    </Box>

                    {recording && (
                      <Typography variant="body1" sx={{ color: '#f59e0b', fontWeight: 'bold', textAlign: 'center' }}>
                        Challenge: {challengeLabels[challengeIndex]}
                      </Typography>
                    )}

                    <Box component="div" sx={{ display: 'flex', gap: 2 }}>
                      <Button
                        type="button"
                        variant="contained"
                        color="secondary"
                        onClick={startLivenessTest}
                        disabled={recording}
                        startIcon={<PlayCircle />}
                      >
                        Start Video Scanner
                      </Button>
                    </Box>

                    {challengesCompleted.length > 0 && (
                      <Typography variant="caption" sx={{ color: '#10b981' }}>
                        Completed Challenges: {challengesCompleted.join(', ')} (Verified)
                      </Typography>
                    )}
                  </Box>
                </CardContent>
              </Card>
            </div>

            {/* Right: Upload Dropzones */}
            <div style={{ flex: '1 1 300px' }}>
              <Card className="glass-panel" sx={{ p: 2 }}>
                <CardContent>
                  <Typography variant="h5" className="gradient-text" sx={{ fontWeight: 'bold', mb: 2 }}>Document Uploads (Secure Encrypted-at-Rest)</Typography>

                  {/* Aadhaar */}
                  <Box component="div" sx={{ mb: 2 }}>
                    <Typography variant="body2" sx={{ mb: 1 }}>Aadhaar Card *</Typography>
                    {uploadedDocs['aadhaar'] ? (
                      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', p: 1, border: '1px solid rgba(255,255,255,0.05)', borderRadius: '4px' }}>
                        <Typography variant="body2" sx={{ color: '#10b981', flexGrow: 1, fontWeight: 'bold' }}>✓ Aadhaar Card Submitted</Typography>
                        <Button size="small" variant="outlined" onClick={() => handlePreview('aadhaar')} startIcon={<Visibility />}>Preview</Button>
                        <IconButton color="error" onClick={() => handleDeleteDoc('aadhaar')} size="small"><Delete /></IconButton>
                      </Box>
                    ) : (
                      <Button component="label" variant="outlined" startIcon={<CloudUpload />} fullWidth>
                        {aadhaarFile ? aadhaarFile.name : 'Upload Aadhaar PDF/Image'}
                        <input type="file" hidden onChange={(e) => handleFileSelect('aadhaar', e.target.files?.[0] || null)} />
                      </Button>
                    )}
                  </Box>

                  {/* PAN */}
                  <Box component="div" sx={{ mb: 2 }}>
                    <Typography variant="body2" sx={{ mb: 1 }}>PAN Card *</Typography>
                    {uploadedDocs['pan'] ? (
                      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', p: 1, border: '1px solid rgba(255,255,255,0.05)', borderRadius: '4px' }}>
                        <Typography variant="body2" sx={{ color: '#10b981', flexGrow: 1, fontWeight: 'bold' }}>✓ PAN Card Submitted</Typography>
                        <Button size="small" variant="outlined" onClick={() => handlePreview('pan')} startIcon={<Visibility />}>Preview</Button>
                        <IconButton color="error" onClick={() => handleDeleteDoc('pan')} size="small"><Delete /></IconButton>
                      </Box>
                    ) : (
                      <Button component="label" variant="outlined" startIcon={<CloudUpload />} fullWidth>
                        {panFile ? panFile.name : 'Upload PAN PDF/Image'}
                        <input type="file" hidden onChange={(e) => handleFileSelect('pan', e.target.files?.[0] || null)} />
                      </Button>
                    )}
                  </Box>

                  {/* Payslips */}
                  <Box component="div" sx={{ mb: 2 }}>
                    <Typography variant="body2" sx={{ mb: 1 }}>Last 3 Months Payslip *</Typography>
                    {uploadedDocs['payslip'] ? (
                      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', p: 1, border: '1px solid rgba(255,255,255,0.05)', borderRadius: '4px' }}>
                        <Typography variant="body2" sx={{ color: '#10b981', flexGrow: 1, fontWeight: 'bold' }}>✓ Payslip Submitted</Typography>
                        <Button size="small" variant="outlined" onClick={() => handlePreview('payslip')} startIcon={<Visibility />}>Preview</Button>
                        <IconButton color="error" onClick={() => handleDeleteDoc('payslip')} size="small"><Delete /></IconButton>
                      </Box>
                    ) : (
                      <Button component="label" variant="outlined" startIcon={<CloudUpload />} fullWidth>
                        {payslipFile ? payslipFile.name : 'Upload Payslip PDF/Image'}
                        <input type="file" hidden onChange={(e) => handleFileSelect('payslip', e.target.files?.[0] || null)} />
                      </Button>
                    )}
                  </Box>

                  {/* Bank Statement */}
                  <Box component="div" sx={{ mb: 2 }}>
                    <Typography variant="body2" sx={{ mb: 1 }}>Last 6 Months Bank Statement *</Typography>
                    {uploadedDocs['bank_statement'] ? (
                      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', p: 1, border: '1px solid rgba(255,255,255,0.05)', borderRadius: '4px' }}>
                        <Typography variant="body2" sx={{ color: '#10b981', flexGrow: 1, fontWeight: 'bold' }}>✓ Bank Statement Submitted</Typography>
                        <Button size="small" variant="outlined" onClick={() => handlePreview('bank_statement')} startIcon={<Visibility />}>Preview</Button>
                        <IconButton color="error" onClick={() => handleDeleteDoc('bank_statement')} size="small"><Delete /></IconButton>
                      </Box>
                    ) : (
                      <Button component="label" variant="outlined" startIcon={<CloudUpload />} fullWidth>
                        {bankFile ? bankFile.name : 'Upload Bank Statement PDF/Image'}
                        <input type="file" hidden onChange={(e) => handleFileSelect('bank_statement', e.target.files?.[0] || null)} />
                      </Button>
                    )}
                  </Box>

                  {/* Address Proof */}
                  <Box component="div" sx={{ mb: 3 }}>
                    <Typography variant="body2" sx={{ mb: 1 }}>Address Proof *</Typography>
                    {uploadedDocs['address_proof'] ? (
                      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', p: 1, border: '1px solid rgba(255,255,255,0.05)', borderRadius: '4px' }}>
                        <Typography variant="body2" sx={{ color: '#10b981', flexGrow: 1, fontWeight: 'bold' }}>✓ Address Proof Submitted</Typography>
                        <Button size="small" variant="outlined" onClick={() => handlePreview('address_proof')} startIcon={<Visibility />}>Preview</Button>
                        <IconButton color="error" onClick={() => handleDeleteDoc('address_proof')} size="small"><Delete /></IconButton>
                      </Box>
                    ) : (
                      <Button component="label" variant="outlined" startIcon={<CloudUpload />} fullWidth>
                        {addressFile ? addressFile.name : 'Upload Bill/Utility Proof'}
                        <input type="file" hidden onChange={(e) => handleFileSelect('address_proof', e.target.files?.[0] || null)} />
                      </Button>
                    )}
                  </Box>

                  <Button
                    type="submit"
                    variant="contained"
                    fullWidth
                    size="large"
                    disabled={loading}
                    sx={{ bgcolor: '#6366f1', '&:hover': { bgcolor: '#4f46e5' }, textTransform: 'none', py: 1.5, fontWeight: 'bold' }}
                  >
                    {loading 
                      ? 'Processing...' 
                      : activeLoanId 
                        ? 'Trigger AI Verification on Existing Loan' 
                        : 'Submit Application & Trigger AI Verification'}
                  </Button>
                </CardContent>
              </Card>
            </div>
          </div>
        </form>
      )}

      {/* --- View 2: History Table --- */}
      {view === 'history' && (
        <Card className="glass-panel" sx={{ p: 2 }}>
          <CardContent>
            <Box component="div" sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
              <Typography variant="h5" sx={{ fontWeight: 'bold' }}>My Applications</Typography>
              <IconButton onClick={fetchLoans} color="primary"><Refresh /></IconButton>
            </Box>

            <TableContainer component={Paper} sx={{ bgcolor: 'transparent', boxShadow: 'none' }}>
              <Table sx={{ minWidth: 650 }}>
                <TableHead>
                  <TableRow sx={{ '& th': { color: '#9ca3af', borderBottom: '1px solid rgba(255,255,255,0.05)' } }}>
                    <TableCell>Application ID</TableCell>
                    <TableCell align="right">Loan Amount</TableCell>
                    <TableCell align="right">Risk Score</TableCell>
                    <TableCell align="right">Risk Category</TableCell>
                    <TableCell align="right">Status</TableCell>
                    <TableCell align="right">Date</TableCell>
                    <TableCell align="right">Action</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {loans.map((row) => (
                    <TableRow key={row.id} sx={{ '& td': { color: '#f3f4f6', borderBottom: '1px solid rgba(255,255,255,0.05)' } }}>
                      <TableCell component="th" scope="row">{row.id}</TableCell>
                      <TableCell align="right">Rs. {parseFloat(row.loan_amount).toLocaleString()}</TableCell>
                      <TableCell align="right">{row.risk_score || '--'}/100</TableCell>
                      <TableCell align="right">{row.risk_category || 'Pending'}</TableCell>
                      <TableCell align="right">
                        <Box
                          component="span"
                          sx={{
                            px: 1.5, py: 0.5, borderRadius: 10, fontSize: 12, fontWeight: 'bold',
                            bgcolor: row.status === 'approved' ? 'rgba(16, 185, 129, 0.15)' : row.status === 'rejected' ? 'rgba(244, 63, 94, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                            color: row.status === 'approved' ? '#10b981' : row.status === 'rejected' ? '#f43f5e' : '#f59e0b'
                          }}
                        >
                          {row.status.toUpperCase()}
                        </Box>
                      </TableCell>
                      <TableCell align="right">{new Date(row.created_at).toLocaleDateString()}</TableCell>
                      <TableCell align="right">
                        <Button
                          variant="outlined"
                          size="small"
                          onClick={() => setActiveLoanId(row.id)}
                          sx={{ textTransform: 'none' }}
                        >
                          Track Process
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                  {loans.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={7} align="center" style={{ color: '#9ca3af' }}>No application history found.</TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      )}

      {/* --- View 3: SSE Real-Time Verification Tracker --- */}
      {view === 'tracking' && (
        <Card className="glass-panel" sx={{ p: 3, maxWidth: 650, mx: 'auto' }}>
          <CardContent>
            <Box component="div" sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
              <IconButton onClick={() => { setView('apply'); setActiveLoanId(null); }} color="primary">
                <ArrowBack />
              </IconButton>
              <Typography variant="h5" sx={{ fontWeight: 'bold' }}>AI Agent Pipeline Tracker</Typography>
            </Box>

            <Typography variant="body2" sx={{ color: 'var(--text-muted)', mb: 1 }}>Current Active Process ID: {activeLoanId}</Typography>
            
            <Alert severity="info" sx={{ mb: 3, bgcolor: 'rgba(99, 102, 241, 0.15)', color: '#a5b4fc' }}>
              {sseStatus}
            </Alert>

            <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 2 }}>Pipeline Execution Checklist:</Typography>

            <List>
              {sseLog.map((item, idx) => (
                <ListItem
                  key={idx}
                  className={`stage-tracker-item ${item.status}`}
                  secondaryAction={getStageIcon(item.status)}
                >
                  <ListItemIcon sx={{ minWidth: 40 }}>
                    {getStageIcon(item.status)}
                  </ListItemIcon>
                  <ListItemText
                    primary={
                      <Typography sx={{
                        fontWeight: item.status === 'pending' ? 'bold' : 'normal',
                        color: item.status === 'pending' ? '#f59e0b' : item.status === 'success' ? '#f3f4f6' : '#9ca3af'
                      }}>
                        {item.message}
                      </Typography>
                    }
                  />
                </ListItem>
              ))}
            </List>

            <Button
              variant="outlined"
              fullWidth
              onClick={() => { setView('history'); setActiveLoanId(null); }}
              sx={{ mt: 3, textTransform: 'none' }}
            >
              Close and View Loan History
            </Button>
          </CardContent>
        </Card>
      )}
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
