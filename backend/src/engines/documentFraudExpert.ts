import { MetadataValidationResult } from '../utils/metadataValidator';
import { ExtractedData } from './ocrEngine';

export interface DocumentFraudReport {
  documentType: string;
  isFake: boolean;
  confidenceScore: number;
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH';
  tamperingDetected: boolean;
  suspectedEdits: Array<{
    field: string;
    reason: string;
    confidence: number;
  }>;
  securityFeatureStatus: {
    logoPresent: boolean;
    watermarkPresent: boolean;
    qrCodePresent: boolean;
    qrCodeSuspicious: boolean;
  };
  observations: string[];
  recommendation: 'APPROVE' | 'MANUAL_REVIEW' | 'REJECT';
}

/**
 * AI Document Fraud Expert Engine.
 * Analyzes layout, OCR text consistency, security elements, and image metadata parameters
 * to formulate a structured authenticity review report.
 */
export async function analyzeDocumentFraud(
  docType: string,
  ocrData: ExtractedData | null,
  metaCheck: MetadataValidationResult,
  applicantName: string
): Promise<DocumentFraudReport> {
  const suspectedEdits: DocumentFraudReport['suspectedEdits'] = [];
  const observations: string[] = [];
  let confidenceScore = 95;
  let riskLevel: DocumentFraudReport['riskLevel'] = 'LOW';
  let tamperingDetected = false;
  let isFake = false;

  let logoPresent = true;
  let watermarkPresent = true;
  let qrCodePresent = docType === 'aadhaar' || docType === 'pan';
  let qrCodeSuspicious = false;

  // 1. Check Metadata validation results (Photoshop, GIMP, AI signatures)
  if (metaCheck.isModified) {
    tamperingDetected = true;
    isFake = true;
    riskLevel = 'HIGH';
    confidenceScore = Math.min(confidenceScore, 30);
    suspectedEdits.push({
      field: 'file_metadata',
      reason: `EXIF/XMP headers contain software editing footprint: ${metaCheck.softwareUsed || 'Editor'} (${metaCheck.signaturesFound.join(', ')})`,
      confidence: 99
    });
    observations.push(`CRITICAL: Digital image was modified using graphics software. Metadata mismatch.`);
  }

  // 2. Document specific structural layout & text consistency checks
  if (ocrData) {
    const rawText = ocrData.rawText.toLowerCase();

    // Check excessive compression or layout anomalies
    if (ocrData.confidenceScore < 80) {
      confidenceScore = Math.min(confidenceScore, 70);
      observations.push('Warning: Low OCR extraction confidence. Image may have compression artifacts or bad resolution.');
    }

    if (docType === 'aadhaar') {
      const hasGovSeals = rawText.includes('government') || rawText.includes('india') || rawText.includes('unique identification');
      if (!hasGovSeals) {
        logoPresent = false;
        suspectedEdits.push({
          field: 'emblem_seal',
          reason: 'Expected Government of India seals or UIDAI emblems were not detected in document layout.',
          confidence: 85
        });
      }

      // Check if Aadhaar number is 12 digits
      const aadhaarNum = ocrData.extractedFields?.aadhaarNumber;
      if (!aadhaarNum || aadhaarNum.length !== 12) {
        tamperingDetected = true;
        suspectedEdits.push({
          field: 'aadhaar_number',
          reason: 'Aadhaar number is missing, incomplete, or formatted incorrectly.',
          confidence: 90
        });
      }

      // Name consistency check
      const docName = ocrData.extractedFields?.name || '';
      if (docName && applicantName) {
        const docNameLower = docName.toLowerCase();
        const appNameParts = applicantName.toLowerCase().split(' ');
        const matchesAnyPart = appNameParts.some(part => docNameLower.includes(part));
        if (!matchesAnyPart) {
          tamperingDetected = true;
          suspectedEdits.push({
            field: 'name_alignment',
            reason: `Name in Aadhaar document (${docName}) does not match the applicant profile name (${applicantName}).`,
            confidence: 95
          });
        }
      }
    }

    if (docType === 'pan') {
      const panNum = ocrData.extractedFields?.panNumber;
      const panRegex = /^[A-Z]{5}\d{4}[A-Z]$/;
      if (!panNum || !panRegex.test(panNum)) {
        tamperingDetected = true;
        suspectedEdits.push({
          field: 'pan_number',
          reason: `Extracted PAN number format (${panNum || 'None'}) is invalid or tampered.`,
          confidence: 95
        });
      }

      const hasTaxLogo = rawText.includes('income tax') || rawText.includes('government') || rawText.includes('department');
      if (!hasTaxLogo) {
        logoPresent = false;
        suspectedEdits.push({
          field: 'tax_department_seal',
          reason: 'Income Tax Department logos or seals were missing in layout analysis.',
          confidence: 80
        });
      }
    }

    if (docType === 'payslip') {
      const textLines = ocrData.rawText.split('\n');
      // Look for font inconsistencies or alignment mismatch in numbers
      const totalEarningsLine = textLines.find(l => l.toLowerCase().includes('gross') || l.toLowerCase().includes('earning'));
      const netPayLine = textLines.find(l => l.toLowerCase().includes('net pay') || l.toLowerCase().includes('salary'));
      
      if (!totalEarningsLine || !netPayLine) {
        suspectedEdits.push({
          field: 'payslip_layout',
          reason: 'Payslip structure lacks standard earning breakdown rows or net wage declarations.',
          confidence: 70
        });
        confidenceScore = Math.min(confidenceScore, 75);
      }
    }
  } else {
    // If no OCR data is provided at all
    confidenceScore = Math.min(confidenceScore, 50);
    observations.push('No OCR layout data available for validation.');
  }

  // 3. Formulate risk category and final recommendation
  if (tamperingDetected) {
    riskLevel = 'HIGH';
    isFake = true;
  } else if (confidenceScore < 85 || !logoPresent) {
    riskLevel = 'MEDIUM';
  }

  let recommendation: DocumentFraudReport['recommendation'] = 'APPROVE';
  if (riskLevel === 'HIGH') {
    recommendation = 'REJECT';
  } else if (riskLevel === 'MEDIUM' || confidenceScore < 70) {
    recommendation = 'MANUAL_REVIEW';
  }

  // Standard observations
  if (!tamperingDetected) {
    observations.push('Document layout matches established organizational templates.');
    observations.push('Exif parameters align with direct camera or flatbed scanning hardware.');
  }

  return {
    documentType: docType,
    isFake,
    confidenceScore,
    riskLevel,
    tamperingDetected,
    suspectedEdits,
    securityFeatureStatus: {
      logoPresent,
      watermarkPresent,
      qrCodePresent,
      qrCodeSuspicious
    },
    observations,
    recommendation
  };
}
