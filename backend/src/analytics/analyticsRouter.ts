import { Router } from 'express';
import { authenticateToken } from '../middleware/auth';
import {
  getExecutiveKPIs,
  getVisualizations,
  getAIInsights,
  exportReport,
  scheduleReport,
  getAuditLogs,
  initializeAnalyticsDatabase
} from './analyticsController';

const router = Router();

// Automatically check and set up database schemas on application loading
initializeAnalyticsDatabase().catch((err) => {
  console.error('[Analytics Router] Dynamic schema check initialization failed:', err);
});

router.get('/kpis', authenticateToken as any, getExecutiveKPIs as any);
router.get('/visualizations', authenticateToken as any, getVisualizations as any);
router.get('/insights', authenticateToken as any, getAIInsights as any);
router.get('/export', authenticateToken as any, exportReport as any);
router.post('/schedule', authenticateToken as any, scheduleReport as any);
router.get('/audit-logs', authenticateToken as any, getAuditLogs as any);

export default router;
