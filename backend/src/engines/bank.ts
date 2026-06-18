import { ExtractedData } from './ocrEngine';

export interface BankAnalysisResult {
  passed: boolean;
  score: number; // 0 - 100
  averageBalance: number;
  monthlyCredits: number;
  monthlyDebits: number;
  existingEmis: number;
  salaryDepositVerified: boolean;
  warnings: string[];
}

/**
 * Parses bank statement text, evaluates transactional sanity, and checks salary credit consistency.
 */
export async function analyzeBankStatement(
  verifiedIncome: number,
  ocrResults: Record<string, ExtractedData>
): Promise<BankAnalysisResult> {
  const statement = ocrResults['bank_statement'];
  const warnings: string[] = [];
  let score = 100;

  if (!statement) {
    return {
      passed: false,
      score: 0,
      averageBalance: 0,
      monthlyCredits: 0,
      monthlyDebits: 0,
      existingEmis: 0,
      salaryDepositVerified: false,
      warnings: ['BANK_STATEMENT_NOT_FOUND']
    };
  }

  const fields = statement.extractedFields;
  const avgBal = parseFloat(fields.averageBalance) || 0;
  const creditsList = fields.salaryCredits || [];
  const emisList = fields.emis || [];

  // Calculate averages
  let totalSalaryCredits = 0;
  let salaryDepositVerified = false;

  creditsList.forEach((credit: any) => {
    const amt = parseFloat(credit.amount) || 0;
    totalSalaryCredits += amt;
    // Check if any deposit matches verified income from payslip closely
    if (verifiedIncome > 0 && Math.abs(amt - verifiedIncome) / verifiedIncome < 0.05) {
      salaryDepositVerified = true;
    }
  });

  const monthlyCredits = creditsList.length ? Math.round(totalSalaryCredits / creditsList.length) : 0;

  // Track regular EMIs
  let totalEmis = 0;
  emisList.forEach((emi: any) => {
    totalEmis += parseFloat(emi.amount) || 0;
  });

  // Warnings & Scoring deductions
  if (!salaryDepositVerified && verifiedIncome > 0) {
    warnings.push('SALARY_CREDIT_NOT_FOUND_IN_BANK_STATEMENT');
    score -= 30;
  }

  if (avgBal < 5000) {
    warnings.push('LOW_AVERAGE_MONTHLY_BALANCE');
    score -= 20;
  }

  if (avgBal < 0) {
    warnings.push('ACCOUNT_OVERDRAFT_DETECTED');
    score -= 40;
  }

  // Monthly debits simulation
  const simulatedDebits = Math.round(monthlyCredits * 0.8) + totalEmis;

  const passed = score >= 50;

  return {
    passed,
    score: Math.max(0, score),
    averageBalance: avgBal,
    monthlyCredits: monthlyCredits || verifiedIncome,
    monthlyDebits: simulatedDebits,
    existingEmis: totalEmis,
    salaryDepositVerified,
    warnings
  };
}
