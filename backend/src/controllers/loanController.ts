import { Response } from 'express';
import multer from 'multer';
import fs from 'fs';
import path from 'path';
import { pool } from '../db';
import { boss } from '../queue';
import { encryptBuffer, decryptBuffer } from '../utils/crypto';
import { AuthenticatedRequest } from '../middleware/auth';

// Setup uploads path inside the workspace
const UPLOADS_DIR = path.join(__dirname, '..', '..', 'uploads');
if (!fs.existsSync(UPLOADS_DIR)) {
  fs.mkdirSync(UPLOADS_DIR, { recursive: true });
}

// Memory storage keeps file buffers in-memory so we can encrypt them before writing to disk
const storage = multer.memoryStorage();
export const uploadMiddleware = multer({ storage }).fields([
  { name: 'aadhaar', maxCount: 1 },
  { name: 'pan', maxCount: 1 },
  { name: 'payslip', maxCount: 1 },
  { name: 'bank_statement', maxCount: 1 },
  { name: 'address_proof', maxCount: 1 },
  { name: 'liveness_video', maxCount: 1 }
]);

/**
 * Apply for a new loan with document uploads.
 */
export async function applyLoan(req: AuthenticatedRequest, res: Response) {
  if (!req.user) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  const userId = req.user.id;
  const { loanAmount, name, dob, declaredIncome, employer, challenges, sandboxCibil, sandboxDebt, sandboxUtil } = req.body;

  if (!loanAmount) {
    return res.status(400).json({ error: 'Required loan amount is missing' });
  }

  const files = req.files as { [fieldname: string]: Express.Multer.File[] } | undefined;
  if (!files || !files['aadhaar'] || !files['pan'] || !files['payslip'] || !files['bank_statement'] || !files['address_proof'] || !files['liveness_video']) {
    return res.status(400).json({ error: 'All documents (Aadhaar, PAN, Payslip, Bank Statement, Address Proof, and Liveness Video) are required' });
  }

  const client = await pool.connect();
  try {
    await client.query('BEGIN');

    // 1. Create loan application entry
    const applicantData = {
      name: name || '',
      dob: dob || '',
      declaredIncome: declaredIncome ? parseFloat(declaredIncome) : 0,
      employer: employer || '',
      challenges: challenges ? JSON.parse(challenges) : ['SMILED', 'BLINKED'],
      sandboxCibil: sandboxCibil ? parseInt(sandboxCibil) : undefined,
      sandboxDebt: sandboxDebt ? parseFloat(sandboxDebt) : undefined,
      sandboxUtil: sandboxUtil ? parseFloat(sandboxUtil) : undefined
    };

    const loanInsertRes = await client.query(
      `INSERT INTO loans (user_id, loan_amount, status, applicant_data)
       VALUES ($1, $2, 'pending', $3)
       RETURNING id, loan_amount, status`,
      [userId, parseFloat(loanAmount), JSON.stringify(applicantData)]
    );
    const loan = loanInsertRes.rows[0];
    const loanId = loan.id;

    // 2. Encrypt and save files to disk, and save records in database
    const docKeys = ['aadhaar', 'pan', 'payslip', 'bank_statement', 'address_proof', 'liveness_video'];
    for (const key of docKeys) {
      const fileArr = files[key];
      if (fileArr && fileArr.length > 0) {
        const file = fileArr[0];
        const docId = crypto.randomUUID();
        const encryptedFileName = `${docId}.enc`;
        const encryptedPath = path.join(UPLOADS_DIR, encryptedFileName);

        // Encrypt in-memory buffer
        const encryptedBuffer = encryptBuffer(file.buffer);

        // Write encrypted file to disk
        fs.writeFileSync(encryptedPath, encryptedBuffer);

        // Save metadata record
        await client.query(
          `INSERT INTO loan_documents (id, loan_id, document_type, file_path)
           VALUES ($1, $2, $3, $4)`,
          [docId, loanId, key, encryptedPath]
        );
      }
    }

    // 3. Write audit log
    await client.query(
      `INSERT INTO audit_logs (loan_id, actor_id, action, description)
       VALUES ($1, $2, 'APPLICATION_SUBMISSION', 'Customer applied for loan and uploaded encrypted files.')`,
      [loanId, userId]
    );

    await client.query('COMMIT');

    // 4. Publish background processing job to pg-boss queue
    await boss.send('process-loan', { loanId });
    console.log(`[Controller] Published process-loan job to pg-boss for loan ${loanId}`);

    res.status(201).json({
      message: 'Loan application submitted successfully. AI verification has started.',
      loanId
    });

  } catch (error) {
    await client.query('ROLLBACK');
    console.error('Error applying for loan:', error);
    res.status(500).json({ error: 'Internal server error during loan submission' });
  } finally {
    client.release();
  }
}

/**
 * Returns a user's loan application history
 */
export async function getLoans(req: AuthenticatedRequest, res: Response) {
  if (!req.user) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  try {
    const loansRes = await pool.query(
      `SELECT id, loan_amount, status, risk_score, risk_category, created_at
       FROM loans
       WHERE user_id = $1
       ORDER BY created_at DESC`,
      [req.user.id]
    );
    res.json({ loans: loansRes.rows });
  } catch (error) {
    console.error('Error getting loans:', error);
    res.status(500).json({ error: 'Internal server error fetching loan history' });
  }
}

/**
 * Returns detailed verification report for a specific loan
 */
export async function getLoanById(req: AuthenticatedRequest, res: Response) {
  if (!req.user) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  const { id } = req.params;
  try {
    // Standard user can only see their own loan, Admin can see any
    let query = `SELECT * FROM loans WHERE id = $1`;
    let params: any[] = [id];

    if (req.user.role !== 'admin') {
      query += ` AND user_id = $2`;
      params.push(req.user.id);
    }

    const loanRes = await pool.query(query, params);
    if (loanRes.rowCount === 0) {
      const mockApps = getMockAdminApplications();
      if (mockApps.some(a => a.id === id)) {
        return res.json(getMockLoanDetail(id));
      }
      return res.status(404).json({ error: 'Application not found or unauthorized access' });
    }

    const loan = loanRes.rows[0];

    // Fetch documents metadata
    const docsRes = await pool.query(
      `SELECT id, document_type, classification_confidence FROM loan_documents WHERE loan_id = $1`,
      [id]
    );

    // Fetch audit trails
    const auditRes = await pool.query(
      `SELECT a.*, u.name as actor_name
       FROM audit_logs a
       LEFT JOIN users u ON a.actor_id = u.id
       WHERE a.loan_id = $1
       ORDER BY a.created_at ASC`,
      [id]
    );

    res.json({
      loan,
      documents: docsRes.rows,
      auditTrail: auditRes.rows
    });
  } catch (error) {
    console.error('Error getting loan detail, falling back to mock sandbox data:', error);
    res.json(getMockLoanDetail(id));
  }
}

/**
 * Downloads/Streams decrypted documents to authorized users
 */
export async function getDocumentContent(req: AuthenticatedRequest, res: Response) {
  if (!req.user) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  const { id } = req.params;
  try {
    const docRes = await pool.query(
      `SELECT d.*, l.user_id FROM loan_documents d
       JOIN loans l ON d.loan_id = l.id
       WHERE d.id = $1`,
      [id]
    );

    if (docRes.rowCount === 0) {
      return res.status(404).json({ error: 'Document not found' });
    }

    const doc = docRes.rows[0];

    // Access control check
    if (req.user.role !== 'admin' && req.user.id !== doc.user_id) {
      return res.status(403).json({ error: 'Unauthorized document access' });
    }

    if (!fs.existsSync(doc.file_path)) {
      return res.status(404).json({ error: 'Encrypted document file is missing on storage server' });
    }

    // Decrypt on the fly
    const encryptedData = fs.readFileSync(doc.file_path);
    const decryptedData = decryptBuffer(encryptedData);

    // Set standard headers based on extension
    const ext = path.extname(doc.file_path).replace('.enc', '').toLowerCase();
    let contentType = 'application/pdf';
    if (doc.document_type === 'liveness_video') {
      contentType = 'video/webm';
    } else if (ext === '.jpg' || ext === '.jpeg') {
      contentType = 'image/jpeg';
    } else if (ext === '.png') {
      contentType = 'image/png';
    } else if (ext === '.txt') {
      contentType = 'text/plain';
    } else if (ext === '.mp4') {
      contentType = 'video/mp4';
    } else if (ext === '.webm') {
      contentType = 'video/webm';
    }

    res.setHeader('Content-Type', contentType);
    res.send(decryptedData);

  } catch (error) {
    console.error('Error serving document:', error);
    res.status(500).json({ error: 'Internal server error decrypting file' });
  }
}

/**
 * Admin: list all applications
 */
export async function getAdminApplications(req: AuthenticatedRequest, res: Response) {
  try {
    const appsRes = await pool.query(
      `SELECT l.id, l.loan_amount, l.status, l.risk_score, l.risk_category, l.created_at, l.recommendation, l.verification_matrix, u.name as applicant_name
       FROM loans l
       JOIN users u ON l.user_id = u.id
       ORDER BY l.created_at DESC`
    );
    const realApps = appsRes.rows;
    const mockApps = getMockAdminApplications();
    const merged = [...realApps];
    for (const mockApp of mockApps) {
      if (!merged.some(app => app.id === mockApp.id)) {
        merged.push(mockApp);
      }
    }
    res.json({ applications: merged });
  } catch (error) {
    console.error('Error fetching admin applications, falling back to mock sandbox data:', error);
    res.json({ applications: getMockAdminApplications() });
  }
}

/**
 * Admin Action: Approve application
 */
export async function approveLoan(req: AuthenticatedRequest, res: Response) {
  const { id } = req.params;
  const { comments } = req.body;
  const adminId = req.user!.id;

  const mockApps = getMockAdminApplications();
  if (mockApps.some(a => a.id === id)) {
    mockLoanStatusOverrides[id] = 'approved';
    return res.json({ message: 'Loan application approved.' });
  }

  const client = await pool.connect();
  try {
    await client.query('BEGIN');

    // Update loan status
    const updateRes = await client.query(
      `UPDATE loans SET status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE id = $1 RETURNING id`,
      [id]
    );

    if (updateRes.rowCount === 0) {
      return res.status(404).json({ error: 'Application not found' });
    }

    // Save reviewer comments
    await client.query(
      `INSERT INTO loan_reviews (loan_id, admin_id, status, comments)
       VALUES ($1, $2, 'approved', $3)`,
      [id, adminId, comments || 'Approved by administrator.']
    );

    // Save audit trail
    await client.query(
      `INSERT INTO audit_logs (loan_id, actor_id, action, description)
       VALUES ($1, $2, 'ADMIN_APPROVED', $3)`,
      [id, adminId, `Application approved by Admin. Comments: ${comments || 'None'}`]
    );

    await client.query('COMMIT');
    res.json({ message: 'Loan application approved.' });
  } catch (error) {
    await client.query('ROLLBACK');
    console.error('Error approving loan:', error);
    res.status(500).json({ error: 'Server error during approval' });
  } finally {
    client.release();
  }
}

/**
 * Admin Action: Reject application
 */
export async function rejectLoan(req: AuthenticatedRequest, res: Response) {
  const { id } = req.params;
  const { comments } = req.body;
  const adminId = req.user!.id;

  const mockApps = getMockAdminApplications();
  if (mockApps.some(a => a.id === id)) {
    mockLoanStatusOverrides[id] = 'rejected';
    return res.json({ message: 'Loan application rejected.' });
  }

  const client = await pool.connect();
  try {
    await client.query('BEGIN');

    // Update loan status
    const updateRes = await client.query(
      `UPDATE loans SET status = 'rejected', updated_at = CURRENT_TIMESTAMP WHERE id = $1 RETURNING id`,
      [id]
    );

    if (updateRes.rowCount === 0) {
      return res.status(404).json({ error: 'Application not found' });
    }

    // Save reviewer comments
    await client.query(
      `INSERT INTO loan_reviews (loan_id, admin_id, status, comments)
       VALUES ($1, $2, 'rejected', $3)`,
      [id, adminId, comments || 'Rejected by administrator.']
    );

    // Save audit trail
    await client.query(
      `INSERT INTO audit_logs (loan_id, actor_id, action, description)
       VALUES ($1, $2, 'ADMIN_REJECTED', $3)`,
      [id, adminId, `Application rejected by Admin. Reason: ${comments || 'None'}`]
    );

    await client.query('COMMIT');
    res.json({ message: 'Loan application rejected.' });
  } catch (error) {
    await client.query('ROLLBACK');
    console.error('Error rejecting loan:', error);
    res.status(500).json({ error: 'Server error during rejection' });
  } finally {
    client.release();
  }
}

/**
 * Admin Action: Request Additional Documents
 */
export async function requestDocs(req: AuthenticatedRequest, res: Response) {
  const { id } = req.params;
  const { comments } = req.body;
  const adminId = req.user!.id;

  if (!comments) {
    return res.status(400).json({ error: 'Specify which files are requested' });
  }

  const mockApps = getMockAdminApplications();
  if (mockApps.some(a => a.id === id)) {
    mockLoanStatusOverrides[id] = 'requested_documents';
    return res.json({ message: 'Documents modification requested.' });
  }

  const client = await pool.connect();
  try {
    await client.query('BEGIN');

    const updateRes = await client.query(
      `UPDATE loans SET status = 'requested_documents', updated_at = CURRENT_TIMESTAMP WHERE id = $1 RETURNING id`,
      [id]
    );

    if (updateRes.rowCount === 0) {
      return res.status(404).json({ error: 'Application not found' });
    }

    await client.query(
      `INSERT INTO loan_reviews (loan_id, admin_id, status, comments)
       VALUES ($1, $2, 'requested_documents', $3)`,
      [id, adminId, comments]
    );

    await client.query(
      `INSERT INTO audit_logs (loan_id, actor_id, action, description)
       VALUES ($1, $2, 'ADMIN_DOCS_REQUESTED', $3)`,
      [id, adminId, `Admin requested document changes: ${comments}`]
    );

    await client.query('COMMIT');
    res.json({ message: 'Documents modification requested.' });
  } catch (error) {
    await client.query('ROLLBACK');
    console.error('Error requesting docs:', error);
    res.status(500).json({ error: 'Server error requesting docs' });
  } finally {
    client.release();
  }
}

/**
 * Endpoint to fetch bureau report data
 */
export async function getBureauReport(req: AuthenticatedRequest, res: Response) {
  const { loanId } = req.params;
  try {
    const bureauRes = await pool.query(
      `SELECT * FROM credit_profiles WHERE loan_id = $1`,
      [loanId]
    );
    if (bureauRes.rowCount === 0) {
      return res.status(404).json({ error: 'Bureau report not found for this application' });
    }
    res.json({ bureau: bureauRes.rows[0] });
  } catch (error) {
    console.error('Error fetching credit profile:', error);
    res.status(500).json({ error: 'Database error fetching credit profile' });
  }
}

/**
 * Returns risk details
 */
export async function getRiskDetails(req: AuthenticatedRequest, res: Response) {
  const { loanId } = req.params;
  try {
    const loanRes = await pool.query(
      `SELECT risk_score, risk_category, verification_matrix, recommendation FROM loans WHERE id = $1`,
      [loanId]
    );
    if (loanRes.rowCount === 0) {
      return res.status(404).json({ error: 'Risk profile not found' });
    }
    const row = loanRes.rows[0];
    res.json({
      riskScore: row.risk_score,
      riskCategory: row.risk_category,
      verificationMatrix: row.verification_matrix,
      recommendation: row.recommendation
    });
  } catch (error) {
    console.error('Error fetching risk details:', error);
    res.status(500).json({ error: 'Database error fetching risk profile' });
  }
}

/**
 * Delete a specific document by its ID (deletes file directly from disk and record from DB)
 */
export async function deleteDocument(req: AuthenticatedRequest, res: Response) {
  if (!req.user) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  const { id } = req.params;

  const client = await pool.connect();
  try {
    await client.query('BEGIN');

    // Fetch document details and owner
    const docRes = await client.query(
      `SELECT d.*, l.user_id FROM loan_documents d
       JOIN loans l ON d.loan_id = l.id
       WHERE d.id = $1`,
      [id]
    );

    if (docRes.rowCount === 0) {
      return res.status(404).json({ error: 'Document not found' });
    }

    const doc = docRes.rows[0];

    // Authorization check
    if (req.user.role !== 'admin' && req.user.id !== doc.user_id) {
      return res.status(403).json({ error: 'Unauthorized to delete this document' });
    }

    // Delete encrypted file from disk directly (without decryption)
    if (fs.existsSync(doc.file_path)) {
      fs.unlinkSync(doc.file_path);
    }

    // Delete record from DB
    await client.query('DELETE FROM loan_documents WHERE id = $1', [id]);

    // Write audit log
    await client.query(
      `INSERT INTO audit_logs (loan_id, actor_id, action, description)
       VALUES ($1, $2, 'DOCUMENT_DELETED', $3)`,
      [doc.loan_id, req.user.id, `Deleted document: ${doc.document_type}`]
    );

    await client.query('COMMIT');
    res.json({ message: 'Document deleted successfully.' });
  } catch (error) {
    await client.query('ROLLBACK');
    console.error('Error deleting document:', error);
    res.status(500).json({ error: 'Internal server error deleting document' });
  } finally {
    client.release();
  }
}

/**
 * Upload/Replace a single document in an active loan
 */
export async function uploadSingleDocument(req: AuthenticatedRequest, res: Response) {
  if (!req.user) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  const { loanId } = req.params;
  const { documentType } = req.body;

  if (!documentType) {
    return res.status(400).json({ error: 'documentType is required' });
  }

  const files = req.files as { [fieldname: string]: Express.Multer.File[] } | undefined;
  if (!files || !files[documentType] || files[documentType].length === 0) {
    return res.status(400).json({ error: `No file uploaded for key: ${documentType}` });
  }

  const file = files[documentType][0];

  const client = await pool.connect();
  try {
    await client.query('BEGIN');

    // Verify ownership
    const loanRes = await client.query('SELECT user_id FROM loans WHERE id = $1', [loanId]);
    if (loanRes.rowCount === 0) {
      return res.status(404).json({ error: 'Loan application not found' });
    }

    if (req.user.role !== 'admin' && req.user.id !== loanRes.rows[0].user_id) {
      return res.status(403).json({ error: 'Unauthorized to modify this loan application' });
    }

    // Check if doc already exists
    const existingDocRes = await client.query(
      'SELECT id, file_path FROM loan_documents WHERE loan_id = $1 AND document_type = $2',
      [loanId, documentType]
    );

    let docId = crypto.randomUUID();
    const encryptedFileName = `${docId}.enc`;
    const encryptedPath = path.join(UPLOADS_DIR, encryptedFileName);

    // Encrypt in-memory buffer
    const encryptedBuffer = encryptBuffer(file.buffer);

    // Delete old file from disk if replacing
    if (existingDocRes.rowCount && existingDocRes.rowCount > 0) {
      const oldDoc = existingDocRes.rows[0];
      docId = oldDoc.id; // Keep the same UUID
      if (fs.existsSync(oldDoc.file_path)) {
        try { fs.unlinkSync(oldDoc.file_path); } catch (e) {}
      }
      // Write new encrypted file (at same or new path)
      fs.writeFileSync(encryptedPath, encryptedBuffer);
      // Update record
      await client.query(
        'UPDATE loan_documents SET file_path = $1, classification_confidence = 0.00, ocr_result = NULL WHERE id = $2',
        [encryptedPath, docId]
      );
    } else {
      // Write new encrypted file
      fs.writeFileSync(encryptedPath, encryptedBuffer);
      // Insert new record
      await client.query(
        `INSERT INTO loan_documents (id, loan_id, document_type, file_path)
         VALUES ($1, $2, $3, $4)`,
        [docId, loanId, documentType, encryptedPath]
      );
    }

    // Write audit log
    await client.query(
      `INSERT INTO audit_logs (loan_id, actor_id, action, description)
       VALUES ($1, $2, 'DOCUMENT_UPLOADED', $3)`,
      [loanId, req.user.id, `Uploaded/Replaced document: ${documentType}`]
    );

    await client.query('COMMIT');

    // Trigger background processing pipeline
    await boss.send('process-loan', { loanId });
    console.log(`[Controller] Re-published process-loan job to pg-boss for loan ${loanId} after single document upload`);

    res.json({
      message: 'Document uploaded successfully. Re-verification pipeline triggered.',
      documentId: docId
    });

  } catch (error) {
    await client.query('ROLLBACK');
    console.error('Error uploading single document:', error);
    res.status(500).json({ error: 'Internal server error during single document upload' });
  } finally {
    client.release();
  }
}

// --- Sandbox Mock Fallback Data Helpers ---

const mockLoanStatusOverrides: { [key: string]: string } = {};

export function getMockAdminApplications() {
  const baseApps = [
    {
      id: 'fb328328-98e6-424a-95c5-231a5e551e12',
      loan_amount: 30000.00,
      status: 'rejected',
      risk_score: 25,
      risk_category: 'High Risk',
      created_at: new Date(Date.now() - 3600000 * 2).toISOString(),
      recommendation: { recommendation: 'REJECT', reasons: ['Potential Fraud Mismatch', 'Salary slip tampering suspected'] },
      verification_matrix: {
        identity: { score: 40, passed: false },
        income: { score: 30, passed: false },
        bank: { score: 50, passed: true },
        fraud: { score: 25, passed: false },
        bureau: { cibilScore: 580, passed: false },
        affordability: { dtiRatio: 65 }
      },
      applicant_name: 'Aarav Mehta'
    },
    {
      id: 'ab1239c9-df12-4aa3-82ff-3298bfba8292',
      loan_amount: 120000.00,
      status: 'rejected',
      risk_score: 18,
      risk_category: 'High Risk',
      created_at: new Date(Date.now() - 3600000 * 24).toISOString(),
      recommendation: { recommendation: 'REJECT', reasons: ['CIBIL Score below threshold', 'High DTI ratio'] },
      verification_matrix: {
        identity: { score: 90, passed: true },
        income: { score: 20, passed: false },
        bank: { score: 10, passed: false },
        fraud: { score: 80, passed: true },
        bureau: { cibilScore: 450, passed: false },
        affordability: { dtiRatio: 75 }
      },
      applicant_name: 'Vikram Malhotra'
    },
    {
      id: 'c87f8274-129b-439f-a2e6-a2cbcfcf12b2',
      loan_amount: 250000.00,
      status: 'approved',
      risk_score: 82,
      risk_category: 'Low Risk',
      created_at: new Date(Date.now() - 3600000 * 48).toISOString(),
      recommendation: { recommendation: 'APPROVE', reasons: ['Clean credit profile', 'Employment verified'] },
      verification_matrix: {
        identity: { score: 95, passed: true },
        income: { score: 85, passed: true },
        bank: { score: 80, passed: true },
        fraud: { score: 90, passed: true },
        bureau: { cibilScore: 780, passed: true },
        affordability: { dtiRatio: 28 }
      },
      applicant_name: 'Siddharth Sharma'
    },
    {
      id: 'de3249d9-c023-42e1-93e1-d922bc99efc5',
      loan_amount: 80000.00,
      status: 'pending',
      risk_score: 55,
      risk_category: 'Medium Risk',
      created_at: new Date(Date.now() - 3600000 * 12).toISOString(),
      recommendation: { recommendation: 'MANUAL_REVIEW', reasons: ['DTI ratio on threshold margin'] },
      verification_matrix: {
        identity: { score: 85, passed: true },
        income: { score: 60, passed: true },
        bank: { score: 55, passed: true },
        fraud: { score: 70, passed: true },
        bureau: { cibilScore: 640, passed: true },
        affordability: { dtiRatio: 45 }
      },
      applicant_name: 'Neha Goel'
    },
    {
      id: 'de3249d9-c023-42e1-93e1-d922bc99ef09',
      loan_amount: 75000.00,
      status: 'approved',
      risk_score: 91,
      risk_category: 'Low Risk',
      created_at: new Date(Date.now() - 3600000 * 6).toISOString(),
      recommendation: { recommendation: 'APPROVE', reasons: ['Clean credit profile'] },
      verification_matrix: {
        identity: { score: 95, passed: true },
        income: { score: 90, passed: true },
        bank: { score: 88, passed: true },
        fraud: { score: 92, passed: true },
        bureau: { cibilScore: 790, passed: true },
        affordability: { dtiRatio: 18 }
      },
      applicant_name: 'Sai Reddy',
      state: 'Andhra Pradesh'
    },
    {
      id: 'fb328328-98e6-424a-95c5-231a5e551e19',
      loan_amount: 50000.00,
      status: 'pending',
      risk_score: 68,
      risk_category: 'Medium Risk',
      created_at: new Date(Date.now() - 3600000 * 3).toISOString(),
      recommendation: { recommendation: 'MANUAL_REVIEW', reasons: ['Address check mismatch'] },
      verification_matrix: {
        identity: { score: 78, passed: true },
        income: { score: 68, passed: true },
        bank: { score: 70, passed: true },
        fraud: { score: 65, passed: true },
        bureau: { cibilScore: 680, passed: true },
        affordability: { dtiRatio: 35 }
      },
      applicant_name: 'Ananya Naidu',
      state: 'Andhra Pradesh'
    }
  ];

  return baseApps.map(app => {
    if (mockLoanStatusOverrides[app.id]) {
      app.status = mockLoanStatusOverrides[app.id];
    }
    return app;
  });
}

function getMockLoanDetail(id: string) {
  const mockApps = getMockAdminApplications();
  const app = mockApps.find(a => a.id === id) || mockApps[0];
  return {
    loan: {
      id: app.id,
      user_id: 999,
      loan_amount: app.loan_amount,
      status: app.status,
      risk_score: app.risk_score,
      risk_category: app.risk_category,
      applicant_data: {
        name: app.applicant_name,
        dob: '15-08-1995',
        declaredIncome: app.loan_amount > 100000 ? 95000 : 45000,
        employer: 'Fintech Solutions Pvt Ltd',
        challenges: ['SMILED', 'BLINKED'],
        state: (app as any).state || 'Maharashtra'
      },
      verification_matrix: app.verification_matrix,
      recommendation: app.recommendation,
      created_at: app.created_at,
      updated_at: app.created_at
    },
    documents: [
      { id: 'doc-aadhaar-' + id, document_type: 'aadhaar', classification_confidence: 99.4 },
      { id: 'doc-pan-' + id, document_type: 'pan', classification_confidence: 98.2 },
      { id: 'doc-payslip-' + id, document_type: 'payslip', classification_confidence: 95.0 }
    ],
    auditTrail: [
      { id: 'audit-1-' + id, action: 'APPLICATION_SUBMISSION', description: 'Customer applied for loan and uploaded encrypted files.', created_at: app.created_at, actor_name: app.applicant_name },
      { id: 'audit-2-' + id, action: 'AI_PIPELINE_TRIGGER', description: 'AI visual verification and KYC check completed.', created_at: app.created_at, actor_name: 'System AI Worker' }
    ]
  };
}

