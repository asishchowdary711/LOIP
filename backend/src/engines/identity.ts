import { ExtractedData } from './ocrEngine';

export interface IdentityResult {
  passed: boolean;
  score: number; // 0 - 100
  reviewRequired: boolean;
  mismatchFlags: string[];
  details: {
    aadhaarPanNameSimilarity: number;
    aadhaarDobMatch: boolean;
    panDobMatch: boolean;
    aadhaarFormatValid: boolean;
    panFormatValid: boolean;
    marriageNameChangeFlag: boolean;
  };
}

/**
 * Calculates Levenshtein Distance between two strings to gauge spelling similarity.
 */
function getLevenshteinDistance(a: string, b: string): number {
  const matrix: number[][] = [];
  const cleanA = a.trim().toLowerCase();
  const cleanB = b.trim().toLowerCase();

  for (let i = 0; i <= cleanA.length; i++) {
    matrix[i] = [i];
  }
  for (let j = 0; j <= cleanB.length; j++) {
    matrix[0][j] = j;
  }

  for (let i = 1; i <= cleanA.length; i++) {
    for (let j = 1; j <= cleanB.length; j++) {
      matrix[i][j] = Math.min(
        matrix[i - 1][j] + 1,
        matrix[i][j - 1] + 1,
        matrix[i - 1][j - 1] + (cleanA[i - 1] === cleanB[j - 1] ? 0 : 1)
      );
    }
  }
  return matrix[cleanA.length][cleanB.length];
}

function getStringSimilarity(a: string, b: string): number {
  const distance = getLevenshteinDistance(a, b);
  const maxLen = Math.max(a.length, b.length);
  if (maxLen === 0) return 100;
  return Math.round((1 - distance / maxLen) * 100);
}

/**
 * Performs MIDV-500/2020 identity consistency checks across Aadhaar, PAN, and Application data.
 */
export async function verifyIdentity(
  applicantName: string,
  applicantDob: string,
  ocrResults: Record<string, ExtractedData>
): Promise<IdentityResult> {
  const aadhaar = ocrResults['aadhaar'];
  const pan = ocrResults['pan'];

  const mismatchFlags: string[] = [];
  let totalScore = 100;
  let reviewRequired = false;

  // 1. Get values from OCR
  const aadhaarName = aadhaar?.extractedFields.name || '';
  const panName = pan?.extractedFields.name || '';
  const aadhaarNo = aadhaar?.extractedFields.aadhaarNumber || '';
  const panNo = pan?.extractedFields.panNumber || '';
  const aadhaarDob = aadhaar?.extractedFields.dob || '';
  const panDob = pan?.extractedFields.dob || '';

  // 2. Validate formats
  const aadhaarValid = /^\d{12}$/.test(aadhaarNo.replace(/\s/g, ''));
  const panValid = /^[A-Z]{5}\d{4}[A-Z]$/.test(panNo.toUpperCase());

  if (!aadhaarValid) {
    mismatchFlags.push('AADHAAR_FORMAT_INVALID');
    totalScore -= 20;
  }
  if (!panValid) {
    mismatchFlags.push('PAN_FORMAT_INVALID');
    totalScore -= 20;
  }

  // 3. Name comparisons
  const nameSim = getStringSimilarity(aadhaarName, panName);
  const appAadhaarSim = getStringSimilarity(applicantName, aadhaarName);

  // Check for marriage-related name change:
  // Usually, first name is identical, but last name differs (e.g. Jane Smith vs Jane Doe)
  let marriageNameChangeFlag = false;
  const name1Parts = applicantName.trim().toLowerCase().split(/\s+/);
  const name2Parts = aadhaarName.trim().toLowerCase().split(/\s+/);
  
  if (nameSim < 80 && name1Parts[0] === name2Parts[0] && name1Parts.length > 1 && name2Parts.length > 1) {
    marriageNameChangeFlag = true;
    mismatchFlags.push('MARRIAGE_NAME_CHANGE_DETECTED');
    reviewRequired = true; // Demote to manual review rather than rejecting
  } else if (nameSim < 85 || appAadhaarSim < 85) {
    mismatchFlags.push('NAME_MISMATCH');
    totalScore -= 30;
  }

  // 4. DOB comparisons
  // Reformat dates to basic strings for comparison (remove hyphens, slashes, spaces)
  const cleanAppDob = applicantDob.replace(/[\s\-/]/g, '');
  const cleanAadhaarDob = aadhaarDob.replace(/[\s\-/]/g, '');
  const cleanPanDob = panDob.replace(/[\s\-/]/g, '');

  const aadhaarDobMatch = cleanAppDob === cleanAadhaarDob || cleanAadhaarDob.includes(cleanAppDob) || cleanAppDob.includes(cleanAadhaarDob);
  const panDobMatch = cleanAppDob === cleanPanDob || cleanPanDob.includes(cleanAppDob) || cleanAppDob.includes(cleanPanDob);

  if (!aadhaarDobMatch) {
    mismatchFlags.push('AADHAAR_DOB_MISMATCH');
    totalScore -= 15;
  }
  if (!panDobMatch) {
    mismatchFlags.push('PAN_DOB_MISMATCH');
    totalScore -= 15;
  }

  // If score is critically low, fail immediately
  const passed = totalScore >= 60 && !mismatchFlags.includes('AADHAAR_FORMAT_INVALID') && !mismatchFlags.includes('PAN_FORMAT_INVALID');
  if (totalScore < 90) {
    reviewRequired = true;
  }

  return {
    passed,
    score: Math.max(0, totalScore),
    reviewRequired,
    mismatchFlags,
    details: {
      aadhaarPanNameSimilarity: nameSim,
      aadhaarDobMatch,
      panDobMatch,
      aadhaarFormatValid: aadhaarValid,
      panFormatValid: panValid,
      marriageNameChangeFlag
    }
  };
}
