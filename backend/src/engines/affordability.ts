export interface AffordabilityResult {
  passed: boolean;
  score: number; // Trust score (0 - 100)
  disposableIncome: number;
  dtiRatio: number;
  warnings: string[];
}

/**
 * Calculates debt obligations against monthly earnings.
 */
export async function assessAffordability(
  monthlyIncome: number,
  existingEmis: number
): Promise<AffordabilityResult> {
  const warnings: string[] = [];
  const income = monthlyIncome || 1; // Prevent division by zero

  // DTI = Total Monthly Debt (existing EMIs) / Monthly Income * 100
  const dtiRatio = Math.round((existingEmis / income) * 100);

  // Simulated basic monthly expenses (food, rent, utils) estimated at 40% of income
  const basicExpenses = Math.round(income * 0.4);
  const disposableIncome = Math.max(0, income - existingEmis - basicExpenses);

  let trustScore = 100;
  if (dtiRatio < 30) {
    trustScore = 100; // Low Risk
  } else if (dtiRatio <= 50) {
    trustScore = 60; // Medium Risk
    warnings.push('ELEVATED_DEBT_TO_INCOME');
  } else {
    trustScore = 20; // High Risk
    warnings.push('CRITICAL_DEBT_TO_INCOME');
  }

  // Double check disposable income buffer
  if (disposableIncome < 15000) {
    warnings.push('LOW_DISPOSABLE_INCOME_BUFFER');
    trustScore -= 20;
  }

  const passed = trustScore >= 40 && dtiRatio <= 60;

  return {
    passed,
    score: Math.max(0, trustScore),
    disposableIncome,
    dtiRatio,
    warnings
  };
}
