export interface BureauResult {
  passed: boolean;
  score: number; // Credit Trust Score (0 - 100)
  cibilScore: number;
  activeLoans: number;
  outstandingDebt: number;
  creditUtilization: number;
  recentEnquiries: number;
  repaymentHistory: 'On-Time' | 'Missed' | 'Defaults';
  warnings: string[];
}

/**
 * Parses and evaluates credit bureau datasets (CIBIL) for repayment risks.
 */
export async function verifyCreditBureau(
  customScore?: number,
  customDebt?: number,
  customUtilization?: number
): Promise<BureauResult> {
  const warnings: string[] = [];
  
  // Default values simulating normal bureau fetch or synthetic cases
  const cibilScore = customScore !== undefined ? customScore : 760;
  const activeLoans = customDebt !== undefined && customDebt > 50000 ? 3 : 1;
  const outstandingDebt = customDebt !== undefined ? customDebt : 30000;
  const creditUtilization = customUtilization !== undefined ? customUtilization : 25; // in %
  const recentEnquiries = customUtilization !== undefined && customUtilization > 60 ? 5 : 1;
  const repaymentHistory = cibilScore >= 700 ? 'On-Time' : cibilScore >= 600 ? 'Missed' : 'Defaults';

  let trustScore = 100;

  // 1. Evaluate CIBIL score
  if (cibilScore >= 800) {
    trustScore = 100;
  } else if (cibilScore >= 750) {
    trustScore = 85;
  } else if (cibilScore >= 700) {
    trustScore = 70;
  } else if (cibilScore >= 650) {
    trustScore = 55;
    warnings.push('AVERAGE_CIBIL_SCORE');
  } else if (cibilScore >= 550) {
    trustScore = 30;
    warnings.push('POOR_CIBIL_SCORE');
  } else {
    trustScore = 10;
    warnings.push('CRITICAL_CIBIL_SCORE');
  }

  // 2. Extra exposure checks
  if (creditUtilization > 70) {
    warnings.push('EXCESSIVE_CREDIT_UTILIZATION');
    trustScore -= 25;
  } else if (creditUtilization > 50) {
    warnings.push('ELEVATED_CREDIT_UTILIZATION');
    trustScore -= 10;
  }

  if (activeLoans > 4) {
    warnings.push('MULTIPLE_ACTIVE_LOANS_EXPOSURE');
    trustScore -= 15;
  }

  if (recentEnquiries > 4) {
    warnings.push('HIGH_RECENT_CREDIT_ENQUIRIES');
    trustScore -= 15;
  }

  if (repaymentHistory === 'Defaults') {
    warnings.push('HISTORICAL_REPAYMENT_DEFAULTS');
    trustScore -= 40;
  } else if (repaymentHistory === 'Missed') {
    warnings.push('RECENT_MISSED_PAYMENTS');
    trustScore -= 20;
  }

  const passed = trustScore >= 40 && cibilScore >= 550;

  return {
    passed,
    score: Math.max(0, trustScore),
    cibilScore,
    activeLoans,
    outstandingDebt,
    creditUtilization,
    recentEnquiries,
    repaymentHistory,
    warnings
  };
}
