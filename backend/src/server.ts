import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import { initializeDatabase, pool } from './db';
import { startQueue } from './queue';
import { authenticateToken, requireAdmin } from './middleware/auth';
import { register, login, getProfile } from './controllers/authController';
import {
  applyLoan,
  getLoans,
  getLoanById,
  getDocumentContent,
  getAdminApplications,
  approveLoan,
  rejectLoan,
  requestDocs,
  getBureauReport,
  getRiskDetails,
  uploadMiddleware,
  deleteDocument,
  uploadSingleDocument
} from './controllers/loanController';
import { sseClients } from './engines';
import analyticsRouter from './analytics';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 5000;

// Enable CORS and raw body JSON parsing
app.use(cors());
app.use(express.json());

// --- Authentication Routes ---
app.post('/api/auth/register', register);
app.post('/api/auth/login', login);
app.get('/api/auth/profile', authenticateToken as any, getProfile as any);

// --- Customer Loan Routes ---
app.post('/api/loans', authenticateToken as any, uploadMiddleware, applyLoan as any);
app.get('/api/loans', authenticateToken as any, getLoans as any);
app.get('/api/loans/:id', authenticateToken as any, getLoanById as any);

// --- Document Downloader & Modifier (Decrypted-at-Rest Streaming & Management) ---
app.get('/api/documents/:id', authenticateToken as any, getDocumentContent as any);
app.delete('/api/documents/:id', authenticateToken as any, deleteDocument as any);
app.post('/api/loans/:loanId/documents', authenticateToken as any, uploadMiddleware, uploadSingleDocument as any);

// --- Credit Bureau & Risk Accessors ---
app.get('/api/bureau/:loanId', authenticateToken as any, getBureauReport as any);
app.get('/api/risk/:loanId', authenticateToken as any, getRiskDetails as any);

// --- Background Pipeline Triggers & SSE Event Stream ---
app.post('/api/processing/start/:loanId', authenticateToken as any, async (req, res) => {
  const { loanId } = req.params;
  try {
    const checkRes = await pool.query('SELECT 1 FROM loans WHERE id = $1', [loanId]);
    if (checkRes.rowCount === 0) {
      return res.status(404).json({ error: 'Loan application not found' });
    }
    // Re-publish to pg-boss
    const { boss } = require('./queue');
    await boss.send('process-loan', { loanId });
    res.json({ message: 'AI processing pipeline successfully re-triggered.' });
  } catch (error) {
    res.status(500).json({ error: 'Failed to queue processing job' });
  }
});

app.get('/api/processing/status/:loanId', authenticateToken as any, async (req, res) => {
  const { loanId } = req.params;
  try {
    const loanRes = await pool.query('SELECT status, risk_score, risk_category, recommendation FROM loans WHERE id = $1', [loanId]);
    if (loanRes.rowCount === 0) {
      return res.status(404).json({ error: 'Application not found' });
    }
    res.json(loanRes.rows[0]);
  } catch (err) {
    res.status(500).json({ error: 'Server error fetching status' });
  }
});

// Server-Sent Events (SSE) Live tracking stream
app.get('/api/events/:loanId', (req, res) => {
  const { loanId } = req.params;

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders(); // Establish connection immediately

  // Register the client response object
  sseClients.set(loanId, res);
  console.log(`[SSE] Client connected for live updates on loan: ${loanId}`);

  // Send initial connected check
  res.write(`data: ${JSON.stringify({ stage: 'connection', status: 'success', message: 'SSE listener active.' })}\n\n`);

  req.on('close', () => {
    sseClients.delete(loanId);
    console.log(`[SSE] Client disconnected for loan: ${loanId}`);
  });
});

// --- Admin Review Actions ---
app.get('/api/admin/applications', authenticateToken as any, requireAdmin as any, getAdminApplications as any);
app.get('/api/admin/application/:id', authenticateToken as any, requireAdmin as any, getLoanById as any);
app.post('/api/admin/approve/:id', authenticateToken as any, requireAdmin as any, approveLoan as any);
app.post('/api/admin/reject/:id', authenticateToken as any, requireAdmin as any, rejectLoan as any);
app.post('/api/admin/request-documents/:id', authenticateToken as any, requireAdmin as any, requestDocs as any);

// --- Analytics & Reporting Module Routes (Module 12) ---
app.use('/api/analytics', analyticsRouter);

// Sandbox Synthetic Testing Injector
app.post('/api/test-cases/inject', authenticateToken as any, async (req, res) => {
  const { profileType, loanAmount } = req.body;
  const userId = (req as any).user!.id;

  try {
    let applicantName = 'Jane Doe';
    let dob = '15-08-1995';
    let declaredIncome = 85000;
    let employer = 'Fintech Innovators Pvt Ltd';
    let sandboxCibil = 780;
    let sandboxDebt = 15000;
    let sandboxUtil = 20;
    let challenges = ['SMILED', 'BLINKED'];

    if (profileType === 'medium') {
      applicantName = 'Jonny Doe'; // minor name variation
      declaredIncome = 50000;
      sandboxCibil = 640; // average score
      sandboxDebt = 25000; // higher DTI (50%)
      sandboxUtil = 45;
    } else if (profileType === 'negative') {
      applicantName = 'Mismatched Name';
      declaredIncome = 30000;
      sandboxCibil = 450; // very poor
      sandboxDebt = 20000; // DTI (66%)
      sandboxUtil = 75;
      employer = 'Fake Company Corp';
    }

    const applicantData = {
      name: applicantName,
      dob,
      declaredIncome,
      employer,
      challenges,
      sandboxCibil,
      sandboxDebt,
      sandboxUtil
    };

    const client = await pool.connect();
    try {
      await client.query('BEGIN');
      
      const loanInsert = await client.query(
        `INSERT INTO loans (user_id, loan_amount, status, applicant_data)
         VALUES ($1, $2, 'pending', $3) RETURNING id`,
        [userId, loanAmount || 50000, JSON.stringify(applicantData)]
      );
      const loanId = loanInsert.rows[0].id;

      // Seed documents as mocks directly to skip file uploads in sandbox mode
      const docs = ['aadhaar', 'pan', 'payslip', 'bank_statement', 'address_proof', 'liveness_video'];
      for (const d of docs) {
        await client.query(
          `INSERT INTO loan_documents (loan_id, document_type, file_path)
           VALUES ($1, $2, $3)`,
          [loanId, d, `sandbox_mock_${d}.enc`]
        );
      }

      await client.query(
        `INSERT INTO audit_logs (loan_id, actor_id, action, description)
         VALUES ($1, $2, 'APPLICATION_SUBMISSION', $3)`,
        [loanId, userId, `Sandbox injected ${profileType} case loan application.`]
      );

      await client.query('COMMIT');

      // Publish job to pg-boss
      const { boss } = require('./queue');
      await boss.send('process-loan', { loanId });

      res.status(201).json({
        message: `Synthetic ${profileType} profile injected and verification queued.`,
        loanId
      });
    } catch (e: any) {
      await client.query('ROLLBACK');
      throw e;
    } finally {
      client.release();
    }
  } catch (err: any) {
    res.status(500).json({ error: 'Sandbox injection failed: ' + err.message });
  }
});

// --- Startup & Initialization ---
async function startServer() {
  // 1. Prepare database and run tables creation
  await initializeDatabase();

  // 2. Start pg-boss queue and workers
  await startQueue();

  // Check AI visual verification configuration
  if (process.env.GEMINI_API_KEY) {
    console.log('[Express] Google Gemini Multimodal Vision API is configured directly. Visual AI verification enabled.');
  } else if (process.env.OPENROUTER_API_KEY) {
    console.log(`[Express] OpenRouter API key configured. Routing Visual AI verification to model: ${process.env.OPENROUTER_MODEL || 'google/gemini-2.5-flash'}`);
  } else {
    console.log('[Express] WARNING: Neither GEMINI_API_KEY nor OPENROUTER_API_KEY found in .env. Falling back to local offline heuristic validation.');
  }

  // 3. Start listening
  app.listen(PORT, () => {
    console.log(`[Express] Server running on http://localhost:${PORT}`);
  });
}

startServer();

// Trigger restart again 4

