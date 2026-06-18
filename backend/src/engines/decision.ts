import { RiskResult } from './risk';

export interface DecisionResult {
  recommendation: 'APPROVE' | 'MANUAL_REVIEW' | 'REJECT';
  reasons: string[];
  riskBreakdown: {
    kycPassed: boolean;
    incomePassed: boolean;
    creditPassed: boolean;
    fraudDetected: boolean;
    marriageNameChange: boolean;
  };
}

/**
 * Automates the recommendation logic based on system verification parameters.
 */
export async function determineDecision(
  riskResult: RiskResult,
  verificationDetails: {
    kycPassed: boolean;
    kycScore: number;
    incomePassed: boolean;
    creditPassed: boolean;
    cibilScore: number;
    fraudPassed: boolean;
    fraudScore: number;
    marriageNameChange: boolean;
    mismatchFlags: string[];
    incomeWarnings: string[];
    bankWarnings: string[];
    bureauWarnings: string[];
    affordabilityWarnings: string[];
  }
): Promise<DecisionResult> {
  const reasons: string[] = [];
  const fraudDetected = !verificationDetails.fraudPassed || verificationDetails.fraudScore < 50;

  const riskBreakdown = {
    kycPassed: verificationDetails.kycPassed,
    incomePassed: verificationDetails.incomePassed,
    creditPassed: verificationDetails.creditPassed,
    fraudDetected,
    marriageNameChange: verificationDetails.marriageNameChange,
  };

  // Compile explainable statuses
  if (verificationDetails.kycPassed) {
    reasons.push('✓ Aadhaar Verified');
    reasons.push('✓ PAN Verified');
  } else {
    reasons.push('✕ Identity Verification Failed');
  }

  if (verificationDetails.incomePassed) {
    reasons.push('✓ Salary Verified');
  } else {
    reasons.push('✕ Income Validation Failed');
  }

  // 1. REJECT CONDITIONS
  if (
    fraudDetected ||
    !verificationDetails.kycPassed ||
    riskResult.finalRiskScore <= 30 || // Critical Risk (High Risk category)
    verificationDetails.cibilScore < 550
  ) {
    if (fraudDetected) {
      reasons.push('✕ CRITICAL: High-likelihood Fraud Indicator Triggered');
    }
    if (!verificationDetails.kycPassed) {
      reasons.push('✕ CRITICAL: Identity verification formats or matches failed');
    }
    if (riskResult.finalRiskScore <= 30) {
      reasons.push('✕ CRITICAL: Overall risk profile is in the critical risk tier');
    }
    if (verificationDetails.cibilScore < 550) {
      reasons.push('✕ CRITICAL: Unacceptable credit bureau rating');
    }

    // Add extra warnings to explain
    verificationDetails.mismatchFlags.forEach(f => reasons.push(`⚠ Mismatch: ${f}`));
    verificationDetails.incomeWarnings.forEach(w => reasons.push(`⚠ Income Warn: ${w}`));
    verificationDetails.bankWarnings.forEach(w => reasons.push(`⚠ Bank Warn: ${w}`));
    verificationDetails.bureauWarnings.forEach(w => reasons.push(`⚠ Bureau Warn: ${w}`));

    return {
      recommendation: 'REJECT',
      reasons,
      riskBreakdown,
    };
  }

  // 2. MANUAL REVIEW CONDITIONS
  const minorMismatches = verificationDetails.marriageNameChange || verificationDetails.mismatchFlags.length > 0;
  const mediumRisk = riskResult.finalRiskScore >= 31 && riskResult.finalRiskScore <= 70;
  const creditDoubt = verificationDetails.cibilScore < 700 || verificationDetails.bureauWarnings.length > 0;
  const affordabilityWarn = verificationDetails.affordabilityWarnings.length > 0;

  if (minorMismatches || mediumRisk || creditDoubt || affordabilityWarn) {
    if (verificationDetails.marriageNameChange) {
      reasons.push('⚠ Marriage-related name change detected, flags manual verification');
    }
    if (mediumRisk) {
      reasons.push('⚠ Risk category sits in the medium risk tier');
    }
    if (verificationDetails.cibilScore < 700) {
      reasons.push('⚠ Credit bureau rating is average or fair');
    }
    if (affordabilityWarn) {
      reasons.push('⚠ Elevated debt-to-income (DTI) ratio');
    }

    // Add all warnings as sub-reasons
    verificationDetails.mismatchFlags.forEach(f => {
      if (f !== 'MARRIAGE_NAME_CHANGE_DETECTED') {
        reasons.push(`⚠ Identity Match Detail: ${f}`);
      }
    });
    verificationDetails.incomeWarnings.forEach(w => reasons.push(`⚠ Income Match Detail: ${w}`));
    verificationDetails.bankWarnings.forEach(w => reasons.push(`⚠ Bank Statement Detail: ${w}`));
    verificationDetails.bureauWarnings.forEach(w => reasons.push(`⚠ Credit File Detail: ${w}`));
    verificationDetails.affordabilityWarnings.forEach(w => reasons.push(`⚠ Affordability Detail: ${w}`));

    return {
      recommendation: 'MANUAL_REVIEW',
      reasons,
      riskBreakdown,
    };
  }

  // 3. APPROVE CONDITIONS
  reasons.push('✓ Excellent Risk Trust Profile');
  reasons.push('✓ Healthy Debt-to-Income Affordability');
  reasons.push('✓ Clean Repayment History');

  return {
    recommendation: 'APPROVE',
    reasons,
    riskBreakdown,
  };
}
