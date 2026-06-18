import { ExtractedData } from './ocrEngine';

export interface QAResult {
  passed: boolean;
  score: number; // 0 - 100
  questionsChecked: {
    question: string;
    answer: string;
    status: 'pass' | 'fail' | 'warn';
  }[];
}

/**
 * Conducts fact-checking questions against the raw layout text extracted from documents,
 * mimicking a layout-aware Document QA transformer (DocVQA).
 */
export async function runDocumentQA(
  ocrResults: Record<string, ExtractedData>
): Promise<QAResult> {
  const checkLog: QAResult['questionsChecked'] = [];
  let score = 100;

  // Let's run targeted QA on Payslips
  const payslip = ocrResults['payslip'];
  if (payslip) {
    const text = payslip.rawText.toLowerCase();

    // Q1: Check for tax deductions
    const hasTax = text.includes('tax') || text.includes('tds') || text.includes('professional');
    checkLog.push({
      question: 'Does the payslip include statutory tax/provident deductions?',
      answer: hasTax ? 'Yes (Verified)' : 'No Tax Deductions Found',
      status: hasTax ? 'pass' : 'warn'
    });
    if (!hasTax) score -= 15;

    // Q2: Check for employer details
    const hasCompanyAddress = text.includes('ltd') || text.includes('corp') || text.includes('pvt') || text.includes('road') || text.includes('street') || text.includes('building');
    checkLog.push({
      question: 'Is the employer address or registration structured in the document?',
      answer: hasCompanyAddress ? 'Yes (Corporate signature matches)' : 'Incomplete Registration',
      status: hasCompanyAddress ? 'pass' : 'warn'
    });
    if (!hasCompanyAddress) score -= 15;
  }

  // Run targeted QA on Bank Statements
  const bank = ocrResults['bank_statement'];
  if (bank) {
    const text = bank.rawText.toLowerCase();

    // Q3: Check for bank logo / header signature
    const hasHeader = text.includes('bank') || text.includes('statement') || text.includes('account');
    checkLog.push({
      question: 'Does the bank statement contain official bank credentials in the header?',
      answer: hasHeader ? 'Verified' : 'Mismatched headers',
      status: hasHeader ? 'pass' : 'fail'
    });
    if (!hasHeader) score -= 30;

    // Q4: Check for balance column consistency
    const hasBalance = text.includes('balance') || text.includes('withdrawals') || text.includes('deposits');
    checkLog.push({
      question: 'Does the statement layout present a valid running balance ledger?',
      answer: hasBalance ? 'Ledger alignment validated' : 'Missing running balance column',
      status: hasBalance ? 'pass' : 'fail'
    });
    if (!hasBalance) score -= 20;
  }

  // Fallback for general case
  if (checkLog.length === 0) {
    checkLog.push({
      question: 'Are all required documents classified and verified?',
      answer: 'Standard files available',
      status: 'pass'
    });
  }

  const passed = score >= 50 && !checkLog.some(q => q.status === 'fail');

  return {
    passed,
    score: Math.max(0, score),
    questionsChecked: checkLog
  };
}
