export interface FraudResult {
  passed: boolean;
  score: number; // Trust score (100 = Safe, 0 = Confirmed Fraud)
  fraudFlags: string[];
  details: {
    documentIntegrityScore: number;
    financialAnomaliesFound: boolean;
    employmentBlacklistMatch: boolean;
    behavioralFlags: string[];
  };
}

/**
 * Evaluates document files, bank ledgers, and profile metadata for multiple types of fraud indicators.
 */
export async function detectFraud(
  identityScore: number,
  incomeScore: number,
  bankScore: number,
  mismatchFlags: string[],
  incomeWarnings: string[],
  bankWarnings: string[],
  metadataTamperingAlert: boolean = false,
  metadataSignatures: string[] = []
): Promise<FraudResult> {
  const fraudFlags: string[] = [];
  let trustScore = 100;

  let documentIntegrityScore = 100;
  let financialAnomaliesFound = false;
  let employmentBlacklistMatch = false;
  const behavioralFlags: string[] = [];

  // 1. Identity Fraud checks
  if (mismatchFlags.includes('NAME_MISMATCH') || mismatchFlags.includes('PAN_FORMAT_INVALID')) {
    fraudFlags.push('IDENTITY_SUSPICIOUS');
    trustScore -= 30;
  }

  // 2. Document Fraud checks (tampering simulation & metadata verification)
  if (metadataTamperingAlert) {
    fraudFlags.push('DOCUMENT_METADATA_TAMPERED');
    documentIntegrityScore = Math.min(documentIntegrityScore, 30);
    trustScore -= 50;
    for (const sig of metadataSignatures) {
      behavioralFlags.push(sig);
    }
  }

  if (incomeScore < 60 && incomeWarnings.includes('INVALID_SALARY_DEDUCTION_STRUCTURE')) {
    fraudFlags.push('DOCUMENT_TAMPERING_SUSPECTED');
    documentIntegrityScore = Math.min(documentIntegrityScore, 40);
    trustScore -= 40;
  }

  // 3. Financial Fraud checks
  // Check for "temporary salary parking" (declared income deviation or lack of salary credits)
  if (bankWarnings.includes('SALARY_CREDIT_NOT_FOUND_IN_BANK_STATEMENT')) {
    fraudFlags.push('TEMPORARY_SALARY_PARKING_INDICATOR');
    financialAnomaliesFound = true;
    trustScore -= 30;
  }

  // 4. Employment Fraud checks
  // Mock check for fake companies (e.g. check if the employer name contains suspicious terms or matching warnings)
  if (incomeWarnings.includes('EMPLOYER_NAME_MISMATCH') && incomeScore < 60) {
    fraudFlags.push('FAKE_EMPLOYER_PROFILING');
    employmentBlacklistMatch = true;
    trustScore -= 25;
  }

  // 5. Behavioral Fraud checks
  // Simulating duplicate checks in database (e.g. random indicator for test case validation)
  if (identityScore < 50) {
    fraudFlags.push('DEVICE_FINGERPRINT_REUSE');
    behavioralFlags.push('MULTIPLE_APPLICATIONS_DETECTED');
    trustScore -= 20;
  }

  const passed = trustScore >= 50 && !fraudFlags.includes('DOCUMENT_TAMPERING_SUSPECTED');

  return {
    passed,
    score: Math.max(0, trustScore),
    fraudFlags,
    details: {
      documentIntegrityScore,
      financialAnomaliesFound,
      employmentBlacklistMatch,
      behavioralFlags
    }
  };
}
