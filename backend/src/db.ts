import { Pool } from 'pg';
import dotenv from 'dotenv';
import bcrypt from 'bcryptjs';

dotenv.config();

const { DB_USER, DB_HOST, DB_PORT, DB_PASSWORD, DB_NAME } = process.env;

// Root client connection configuration to default 'postgres' database
const rootConfig = {
  user: DB_USER || 'postgres',
  host: DB_HOST || 'localhost',
  port: parseInt(DB_PORT || '5432'),
  password: DB_PASSWORD || 'postgres',
  database: 'postgres',
};

// Database connection pool for the loan platform
export const pool = new Pool({
  user: DB_USER || 'postgres',
  host: DB_HOST || 'localhost',
  port: parseInt(DB_PORT || '5432'),
  password: DB_PASSWORD || 'postgres',
  database: DB_NAME || 'digital_loan',
});

/**
 * Ensures that the digital_loan database exists, sets up the table schemas,
 * and seeds initial test users.
 */
export async function initializeDatabase() {
  const rootPool = new Pool(rootConfig);
  try {
    const dbName = DB_NAME || 'digital_loan';
    const checkDbQuery = `SELECT 1 FROM pg_database WHERE datname = $1`;
    const res = await rootPool.query(checkDbQuery, [dbName]);

    if (res.rowCount === 0) {
      console.log(`Database '${dbName}' does not exist. Creating...`);
      // CREATE DATABASE cannot run inside a transaction block, so we execute it directly
      await rootPool.query(`CREATE DATABASE ${dbName}`);
      console.log(`Database '${dbName}' created successfully.`);
    }
  } catch (error) {
    console.error('Error checking/creating database:', error);
  } finally {
    await rootPool.end();
  }

  // Connect to the new database to initialize schemas
  let client;
  try {
    client = await pool.connect();
    console.log('Initializing schemas...');

    // 1. Users Table
    await client.query(`
      CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        email VARCHAR(150) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'admin')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
    `);

    // 2. Loans Table
    await client.query(`
      CREATE TABLE IF NOT EXISTS loans (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        loan_amount NUMERIC(12, 2) NOT NULL,
        status VARCHAR(30) NOT NULL CHECK (status IN ('pending', 'processing', 'approved', 'rejected', 'requested_documents')),
        risk_score INTEGER DEFAULT 0,
        risk_category VARCHAR(20) DEFAULT 'High Risk',
        applicant_data JSONB DEFAULT '{}',
        verification_matrix JSONB DEFAULT '{}',
        recommendation JSONB DEFAULT '{}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
    `);

    // 3. Loan Documents Table
    await client.query(`
      CREATE TABLE IF NOT EXISTS loan_documents (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        loan_id UUID REFERENCES loans(id) ON DELETE CASCADE,
        document_type VARCHAR(50) NOT NULL CHECK (document_type IN ('aadhaar', 'pan', 'payslip', 'bank_statement', 'address_proof', 'liveness_video')),
        file_path VARCHAR(255) NOT NULL,
        classification_confidence NUMERIC(5, 2) DEFAULT 0.00,
        ocr_result TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
    `);

    // 4. Credit Profiles Table
    await client.query(`
      CREATE TABLE IF NOT EXISTS credit_profiles (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        loan_id UUID REFERENCES loans(id) ON DELETE CASCADE,
        cibil_score INTEGER NOT NULL,
        active_loans INTEGER NOT NULL,
        outstanding_debt NUMERIC(12, 2) NOT NULL,
        credit_utilization NUMERIC(5, 2) NOT NULL,
        recent_enquiries INTEGER NOT NULL,
        repayment_history VARCHAR(50) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
    `);

    // 5. Loan Reviews Table
    await client.query(`
      CREATE TABLE IF NOT EXISTS loan_reviews (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        loan_id UUID REFERENCES loans(id) ON DELETE CASCADE,
        admin_id INTEGER REFERENCES users(id),
        status VARCHAR(30) NOT NULL,
        comments TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
    `);

    // 6. Audit Logs Table
    await client.query(`
      CREATE TABLE IF NOT EXISTS audit_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        loan_id UUID REFERENCES loans(id) ON DELETE CASCADE,
        actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        action VARCHAR(100) NOT NULL,
        description TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
    `);
    console.log('Tables verified/created successfully.');

    // Seed Demo User
    const userExist = await client.query('SELECT 1 FROM users WHERE email = $1', ['user@digital-loan.com']);
    if (userExist.rowCount === 0) {
      const userHash = bcrypt.hashSync('user123', 10);
      await client.query(
        "INSERT INTO users (name, email, password_hash, role) VALUES ($1, $2, $3, 'user')",
        ['Demo User', 'user@digital-loan.com', userHash]
      );
      console.log('[Seed] Demo User (user@digital-loan.com / user123) seeded.');
    }

    // Seed Demo Admin
    const adminExist = await client.query('SELECT 1 FROM users WHERE email = $1', ['admin@digital-loan.com']);
    if (adminExist.rowCount === 0) {
      const adminHash = bcrypt.hashSync('admin123', 10);
      await client.query(
        "INSERT INTO users (name, email, password_hash, role) VALUES ($1, $2, $3, 'admin')",
        ['Demo Admin', 'admin@digital-loan.com', adminHash]
      );
      console.log('[Seed] Demo Admin (admin@digital-loan.com / admin123) seeded.');
    }

    console.log('Database initialization complete.');
  } catch (error) {
    console.error('Error initializing tables/seeding:', error);
  } finally {
    if (client) {
      client.release();
    }
  }
}
