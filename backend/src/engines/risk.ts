export interface RiskResult {
  finalRiskScore: number; // 0-100
  riskCategory: 'High Risk' | 'Medium Risk' | 'Low Risk';
  weightsApplied: {
    identity: number;
    income: number;
    bank: number;
    fraud: number;
    credit: number;
    affordability: number;
  };
}

/**
 * Computes the aggregated weighted trust score from the 6 verification engine results.
 * Risk Categories:
 * 0-30 = High Risk (Low trust)
 * 31-70 = Medium Risk (Medium trust)
 * 71-100 = Low Risk (High trust)
 */
export async function calculateRiskScore(subScores: {
  identity: number;
  income: number;
  bank: number;
  fraud: number;
  credit: number;
  affordability: number;
}): Promise<RiskResult> {
  const identityWeight = 0.20;
  const incomeWeight = 0.20;
  const bankWeight = 0.15;
  const fraudWeight = 0.20;
  const creditWeight = 0.15;
  const affordabilityWeight = 0.10;

  const identityContribution = subScores.identity * identityWeight;
  const incomeContribution = subScores.income * incomeWeight;
  const bankContribution = subScores.bank * bankWeight;
  const fraudContribution = subScores.fraud * fraudWeight;
  const creditContribution = subScores.credit * creditWeight;
  const affordabilityContribution = subScores.affordability * affordabilityWeight;

  const finalRiskScore = Math.round(
    identityContribution +
    incomeContribution +
    bankContribution +
    fraudContribution +
    creditContribution +
    affordabilityContribution
  );

  let riskCategory: RiskResult['riskCategory'] = 'High Risk';
  if (finalRiskScore >= 71) {
    riskCategory = 'Low Risk';
  } else if (finalRiskScore >= 31) {
    riskCategory = 'Medium Risk';
  } else {
    riskCategory = 'High Risk';
  }

  return {
    finalRiskScore,
    riskCategory,
    weightsApplied: {
      identity: Math.round(identityContribution),
      income: Math.round(incomeContribution),
      bank: Math.round(bankContribution),
      fraud: Math.round(fraudContribution),
      credit: Math.round(creditContribution),
      affordability: Math.round(affordabilityContribution),
    }
  };
}
