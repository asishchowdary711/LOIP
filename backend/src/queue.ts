import PgBoss from 'pg-boss';
import dotenv from 'dotenv';
import { runLoanProcessingPipeline } from './engines';

dotenv.config();

const { DB_USER, DB_HOST, DB_PORT, DB_PASSWORD, DB_NAME } = process.env;

const connectionString = `postgresql://${DB_USER || 'postgres'}:${DB_PASSWORD || 'postgres'}@${DB_HOST || 'localhost'}:${DB_PORT || '5432'}/${DB_NAME || 'digital_loan'}`;

export const boss = new PgBoss({
  connectionString,
  schema: 'public',
});

/**
 * Initializes and starts pg-boss queue, then registers workers.
 */
export async function startQueue() {
  boss.on('error', (error) => console.error('pg-boss error:', error));

  try {
    await boss.start();
    console.log('pg-boss queue started.');

    // Register job handler for processing loan applications
    await boss.work('process-loan', async (job) => {
      const { loanId } = job.data as { loanId: string };
      console.log(`[Queue Worker] Processing loan application: ${loanId}`);
      try {
        await runLoanProcessingPipeline(loanId);
      } catch (err) {
        console.error(`[Queue Worker] Failed processing loan ${loanId}:`, err);
        throw err; // Fail the job so pg-boss can track it or retry
      }
    });
  } catch (error) {
    console.error('Failed to initialize pg-boss queue:', error);
  }
}
