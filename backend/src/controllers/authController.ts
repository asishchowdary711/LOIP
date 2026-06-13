import { Request, Response } from 'express';
import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { pool } from '../db';
import { AuthenticatedRequest } from '../middleware/auth';

const JWT_SECRET = process.env.JWT_SECRET || 'super-secret-key-1234-loan-platform';

/**
 * Register a new user or admin
 */
export async function register(req: Request, res: Response) {
  const { name, email, password, role } = req.body;

  if (!name || !email || !password) {
    return res.status(400).json({ error: 'Name, email, and password are required' });
  }

  const assignedRole = role === 'admin' ? 'admin' : 'user';

  try {
    // Check if user already exists
    const userExist = await pool.query('SELECT 1 FROM users WHERE email = $1', [email]);
    if (userExist.rowCount && userExist.rowCount > 0) {
      return res.status(400).json({ error: 'Email already registered' });
    }

    // Hash password and save
    const passwordHash = bcrypt.hashSync(password, 10);
    const insertRes = await pool.query(
      'INSERT INTO users (name, email, password_hash, role) VALUES ($1, $2, $3, $4) RETURNING id, name, email, role',
      [name, email, passwordHash, assignedRole]
    );

    const newUser = insertRes.rows[0];

    // Sign JWT
    const token = jwt.sign(
      { id: newUser.id, name: newUser.name, email: newUser.email, role: newUser.role },
      JWT_SECRET,
      { expiresIn: '24h' }
    );

    res.status(201).json({
      token,
      user: {
        id: newUser.id,
        name: newUser.name,
        email: newUser.email,
        role: newUser.role,
      },
    });
  } catch (error) {
    console.error('Registration error:', error);
    res.status(500).json({ error: 'Internal server error during registration' });
  }
}

/**
 * Login user
 */
export async function login(req: Request, res: Response) {
  const { email, password } = req.body;

  if (!email || !password) {
    return res.status(400).json({ error: 'Email and password are required' });
  }

  try {
    const userRes = await pool.query('SELECT * FROM users WHERE email = $1', [email]);
    if (userRes.rowCount === 0) {
      return res.status(401).json({ error: 'Invalid email or password' });
    }

    const user = userRes.rows[0];
    const isPasswordValid = bcrypt.compareSync(password, user.password_hash);
    if (!isPasswordValid) {
      return res.status(401).json({ error: 'Invalid email or password' });
    }

    const token = jwt.sign(
      { id: user.id, name: user.name, email: user.email, role: user.role },
      JWT_SECRET,
      { expiresIn: '24h' }
    );

    res.json({
      token,
      user: {
        id: user.id,
        name: user.name,
        email: user.email,
        role: user.role,
      },
    });
  } catch (error) {
    console.error('Login error:', error);
    res.status(500).json({ error: 'Internal server error during login' });
  }
}

/**
 * Get profile details
 */
export async function getProfile(req: AuthenticatedRequest, res: Response) {
  if (!req.user) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  try {
    const latestLoan = await pool.query(
      'SELECT id, status, applicant_data FROM loans WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1',
      [req.user.id]
    );
    
    let latestApplicantData = null;
    let latestDocuments: any[] = [];
    let latestLoanId = null;
    let latestLoanStatus = null;

    if (latestLoan.rowCount && latestLoan.rowCount > 0) {
      latestLoanId = latestLoan.rows[0].id;
      latestLoanStatus = latestLoan.rows[0].status;
      latestApplicantData = latestLoan.rows[0].applicant_data;
      
      const docsRes = await pool.query(
        'SELECT id, document_type, classification_confidence FROM loan_documents WHERE loan_id = $1',
        [latestLoanId]
      );
      latestDocuments = docsRes.rows;
    }

    res.json({
      user: req.user,
      latestLoanId,
      latestLoanStatus,
      latestApplicantData,
      latestDocuments
    });
  } catch (error) {
    console.error('Error fetching user profile extra details:', error);
    res.json({ user: req.user, latestLoanId: null, latestApplicantData: null, latestDocuments: [] });
  }
}
