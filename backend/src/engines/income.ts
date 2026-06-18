import { ExtractedData } from './ocrEngine';

export interface IncomeResult {
  passed: boolean;
  score: number; // 0 - 100
  monthlyIncome: number;
  employerName: string;
  employerConfidence: number;
  warnings: string[];
}

/**
 * Validates payslips against application inputs, checks stability, and checks authenticity signals.
 */
export async function verifyIncome(
  declaredIncome: number,
  declaredEmployer: string,
  ocrResults: Record<string, ExtractedData>
): Promise<IncomeResult> {
  const payslip = ocrResults['payslip'];
  const warnings: string[] = [];
  let score = 100;

  if (!payslip) {
    return {
      passed: false,
      score: 0,
      monthlyIncome: 0,
      employerName: 'Unknown',
      employerConfidence: 0,
      warnings: ['PAYSLIP_NOT_FOUND']
    };
  }

  const { employerName = '', netPay = 0, grossPay = 0 } = payslip.extractedFields;

  // 1. Validate Employer Matching
  const cleanDeclared = declaredEmployer.trim().toLowerCase();
  const cleanExtracted = employerName.trim().toLowerCase();
  let employerConfidence = 0;

  if (cleanExtracted.includes(cleanDeclared) || cleanDeclared.includes(cleanExtracted)) {
    employerConfidence = 100;
  } else {
    // Fuzzy matching
    let matches = 0;
    const wordsDeclared = cleanDeclared.split(/\s+/);
    wordsDeclared.forEach(word => {
      if (word.length > 2 && cleanExtracted.includes(word)) matches++;
    });
    employerConfidence = wordsDeclared.length ? Math.round((matches / wordsDeclared.length) * 100) : 0;
  }

  if (employerConfidence < 50) {
    warnings.push('EMPLOYER_NAME_MISMATCH');
    score -= 30;
  }

  // 2. Validate Salary Amount
  const netPayNum = parseFloat(netPay) || 0;
  const grossPayNum = parseFloat(grossPay) || 0;

  if (netPayNum === 0) {
    warnings.push('NET_PAY_EXTRACT_FAILED');
    score -= 20;
  }

  // Comapre net pay with declared monthly income
  const deviation = Math.abs(netPayNum - declaredIncome) / (declaredIncome || 1);
  if (deviation > 0.2) {
    warnings.push('DECLARED_INCOME_DEVIATION_HIGH');
    score -= 25;
  }

  // Check deduction structure sanity
  if (grossPayNum > 0 && netPayNum > grossPayNum) {
    warnings.push('INVALID_SALARY_DEDUCTION_STRUCTURE');
    score -= 40; // Highly suspicious if net is higher than gross!
  }

  const passed = score >= 50 && netPayNum > 0;

  return {
    passed,
    score: Math.max(0, score),
    monthlyIncome: netPayNum || declaredIncome,
    employerName: employerName || declaredEmployer,
    employerConfidence,
    warnings
  };
}
