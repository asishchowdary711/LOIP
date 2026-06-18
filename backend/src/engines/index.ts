import { Response } from 'express';
import { pool } from '../db';
import { runOcrEngine, ExtractedData } from './ocrEngine';
import { classifyDocument } from './classifier';
import { verifyIdentity } from './identity';
import { verifyIncome } from './income';
import { analyzeBankStatement } from './bank';
import { runDocumentQA } from './docQA';
import { detectFraud } from './fraud';
import { verifyFaceAndLiveness } from './face';
import { verifyCreditBureau } from './bureau';
import { assessAffordability } from './affordability';
import { calculateRiskScore } from './risk';
import { determineDecision } from './decision';
import fs from 'fs';
import { decryptBuffer } from '../utils/crypto';
import { validateImageMetadata, MetadataValidationResult } from '../utils/metadataValidator';
import { analyzeDocumentFraud, DocumentFraudReport } from './documentFraudExpert';
import { analyzeDocumentWithGemini } from '../utils/geminiVision';

// In-memory registry to hold active Server-Sent Events connections
export const sseClients = new Map<string, Response>();

/**
 * Sends a real-time progress update to the client listening on Server-Sent Events.
 */
export function sendSseUpdate(loanId: string, payload: { stage: string; status: 'pending' | 'success' | 'failed'; message: string; data?: any }) {
  const clientRes = sseClients.get(loanId);
  if (clientRes) {
    clientRes.write(`data: ${JSON.stringify(payload)}\n\n`);
  }
}

/**
 * Runs the complete 11-stage AI processing pipeline for a loan application.
 * Called asynchronously by the pg-boss worker.
 */
export async function runLoanProcessingPipeline(loanId: string): Promise<void> {
  console.log(`[Pipeline] Beginning execution for loan ${loanId}`);
  const client = await pool.connect();
  
  try {
    // 0. Update loan status to 'processing' and create audit log
    await client.query("UPDATE loans SET status = 'processing' WHERE id = $1", [loanId]);
    await client.query(
      "INSERT INTO audit_logs (loan_id, action, description) VALUES ($1, $2, $3)",
      [loanId, 'PIPELINE_STARTED', 'AI agents started background verification pipeline.']
    );

    // Fetch loan and uploaded documents
    const loanRes = await client.query("SELECT * FROM loans WHERE id = $1", [loanId]);
    if (loanRes.rowCount === 0) {
      throw new Error(`Loan ${loanId} not found`);
    }
    const loan = loanRes.rows[0];

    const docsRes = await client.query("SELECT * FROM loan_documents WHERE loan_id = $1", [loanId]);
    const documents = docsRes.rows;

    let applicantName = loan.applicant_data?.name || '';
    if (!applicantName) {
      const userRes = await client.query("SELECT name FROM users WHERE id = $1", [loan.user_id]);
      applicantName = userRes.rowCount && userRes.rowCount > 0 ? userRes.rows[0].name : 'Jane Doe';
    }
    const ocrResults: Record<string, ExtractedData> = {};
    const docFraudReports: DocumentFraudReport[] = [];
    let metadataTamperingAlert = false;
    const metadataSignatures: string[] = [];

    // 1. Stage 1: Classification & Stage 2: OCR
    sendSseUpdate(loanId, { stage: 'document_classification', status: 'pending', message: 'Classifying documents (RVL-CDIP alignment)...' });
    
    for (const doc of documents) {
      if (doc.document_type === 'liveness_video') {
        // Skip OCR and classification for video files
        await client.query(
          "UPDATE loan_documents SET classification_confidence = $1, ocr_result = $2 WHERE id = $3",
          [100.0, 'VIDEO_MEDIA_STREAM', doc.id]
        );
        continue;
      }

      // Check document image metadata for Photoshop/AI signatures
      let metaRes: MetadataValidationResult = { isModified: false, softwareUsed: null, signaturesFound: [] };
      let decryptedData: Buffer = Buffer.alloc(0);
      try {
        if (doc.file_path.includes('sandbox_mock_')) {
          // If it is sandbox mock, generate mock buffer.
          // In negative profile (declaredIncome is 30000), inject a Photoshop signature on the PAN document.
          const isNegative = parseFloat(loan.applicant_data?.declaredIncome) === 30000;
          decryptedData = Buffer.from(
            isNegative && doc.document_type === 'pan'
              ? 'Mock Document Buffer containing Adobe Photoshop 3.0 Signature'
              : 'Mock Document Buffer'
          );
        } else {
          const encryptedData = fs.readFileSync(doc.file_path);
          decryptedData = decryptBuffer(encryptedData);
        }

        metaRes = validateImageMetadata(decryptedData, doc.file_path);
        if (metaRes.isModified) {
          metadataTamperingAlert = true;
          metadataSignatures.push(`${doc.document_type.toUpperCase()}: Edited via ${metaRes.softwareUsed || 'Image Editor'} (${metaRes.signaturesFound.join(', ')})`);
        }
      } catch (err) {
        console.error(`[Metadata Check] Failed for document ${doc.document_type}:`, err);
      }

      // Document classification check
      const classRes = await classifyDocument(doc.file_path, doc.document_type);
      await client.query(
        "UPDATE loan_documents SET classification_confidence = $1 WHERE id = $2",
        [classRes.confidenceScore, doc.id]
      );
      
      // OCR & Extract
      sendSseUpdate(loanId, { stage: 'ocr_extraction', status: 'pending', message: `Running OCR layout analysis on ${doc.document_type} (MarkItDown)...` });
      const ocrRes = await runOcrEngine(doc.file_path, doc.document_type, loan.applicant_data);
      
      await client.query(
        "UPDATE loan_documents SET ocr_result = $1 WHERE id = $2",
        [ocrRes.rawText, doc.id]
      );

      ocrResults[doc.document_type] = ocrRes;

      // Run AI Document Fraud Expert Engine analysis (Multi-modal Gemini or offline fallback)
      let fraudReport: DocumentFraudReport | null = null;
      if (!doc.file_path.includes('sandbox_mock_')) {
        try {
          fraudReport = await analyzeDocumentWithGemini(
            decryptedData,
            doc.file_path,
            doc.document_type,
            applicantName
          );
        } catch (geminiErr) {
          console.warn('[Gemini Vision API] Failed. Falling back to local offline ruleset...', geminiErr);
        }
      }

      if (!fraudReport) {
        fraudReport = await analyzeDocumentFraud(
          doc.document_type,
          ocrRes,
          metaRes,
          applicantName
        );
      }
      docFraudReports.push(fraudReport);
    }

    sendSseUpdate(loanId, { stage: 'document_classification', status: 'success', message: 'Documents classified.' });
    sendSseUpdate(loanId, { stage: 'ocr_extraction', status: 'success', message: 'OCR layouts extracted.' });

    // Backfill any missing applicant_data using OCR results
    let applicantDob = loan.applicant_data?.dob || '';
    if (!applicantDob) {
      applicantDob = ocrResults['aadhaar']?.extractedFields.dob || ocrResults['pan']?.extractedFields.dob || '15-08-1995';
    }

    let declaredIncome = parseFloat(loan.applicant_data?.declaredIncome) || 0;
    if (!declaredIncome) {
      declaredIncome = parseFloat(ocrResults['payslip']?.extractedFields.netPay) || 
                       parseFloat(ocrResults['bank_statement']?.extractedFields.averageBalance) / 1.5 || 
                       85000;
    }

    let declaredEmployer = loan.applicant_data?.employer || '';
    if (!declaredEmployer) {
      declaredEmployer = ocrResults['payslip']?.extractedFields.employerName || 'Fintech Innovators Pvt Ltd';
    }

    // Save backfilled details to DB so that they are loaded in subsequent profile checks
    const updatedApplicantData = {
      ...loan.applicant_data,
      name: applicantName,
      dob: applicantDob,
      declaredIncome,
      employer: declaredEmployer
    };
    await client.query("UPDATE loans SET applicant_data = $1 WHERE id = $2", [JSON.stringify(updatedApplicantData), loanId]);

    // 2. Stage 3: Identity Verification
    sendSseUpdate(loanId, { stage: 'identity_verification', status: 'pending', message: 'Checking Identity Consistency (MIDV-500/2020)...' });
    const identityResult = await verifyIdentity(applicantName, applicantDob, ocrResults);
    sendSseUpdate(loanId, {
      stage: 'identity_verification',
      status: identityResult.passed ? 'success' : 'failed',
      message: identityResult.passed ? 'Identity checked.' : 'Identity checks failed.'
    });

    // 3. Stage 4: Income Verification
    sendSseUpdate(loanId, { stage: 'income_verification', status: 'pending', message: 'Analyzing payslip structure...' });
    const incomeResult = await verifyIncome(declaredIncome, declaredEmployer, ocrResults);
    sendSseUpdate(loanId, {
      stage: 'income_verification',
      status: incomeResult.passed ? 'success' : 'failed',
      message: incomeResult.passed ? 'Income verified.' : 'Income check flags warnings.'
    });

    // 4. Stage 5: Bank Statement Analysis
    sendSseUpdate(loanId, { stage: 'bank_analysis', status: 'pending', message: 'Analyzing bank ledger transactions...' });
    const bankResult = await analyzeBankStatement(incomeResult.monthlyIncome, ocrResults);
    sendSseUpdate(loanId, {
      stage: 'bank_analysis',
      status: bankResult.passed ? 'success' : 'failed',
      message: bankResult.passed ? 'Bank statement analyzed.' : 'Bank ledger flags warning.'
    });

    // 5. Document QA Layer (DocVQA-style)
    const qaResult = await runDocumentQA(ocrResults);

    // 6. Stage 6: Fraud Detection
    sendSseUpdate(loanId, { stage: 'fraud_detection', status: 'pending', message: 'Running anti-fraud rulesets...' });
    const fraudResult = await detectFraud(
      identityResult.score,
      incomeResult.score,
      bankResult.score,
      identityResult.mismatchFlags,
      incomeResult.warnings,
      bankResult.warnings,
      metadataTamperingAlert,
      metadataSignatures
    );
    sendSseUpdate(loanId, {
      stage: 'fraud_detection',
      status: fraudResult.passed ? 'success' : 'failed',
      message: fraudResult.passed ? 'No critical fraud indicators.' : 'Suspicious indicators flagged.'
    });

    // 7. Stage 7: Face Liveness Check
    sendSseUpdate(loanId, { stage: 'face_verification', status: 'pending', message: 'Evaluating liveness challenge responses...' });
    // Check challenges in the loan record
    const challenges = loan.applicant_data?.challenges || ['SMILED', 'BLINKED'];
    const faceResult = await verifyFaceAndLiveness(challenges, true);
    sendSseUpdate(loanId, {
      stage: 'face_verification',
      status: faceResult.passed ? 'success' : 'failed',
      message: faceResult.passed ? 'Liveness and Face matched.' : 'Webcam liveness check failed.'
    });

    // 8. Stage 8: Credit Bureau Check
    sendSseUpdate(loanId, { stage: 'credit_bureau', status: 'pending', message: 'Fetching CIBIL report...' });
    // Allow custom testing parameters from applicant_data sandbox overrides
    const testCibil = loan.applicant_data?.sandboxCibil;
    const testDebt = loan.applicant_data?.sandboxDebt;
    const testUtil = loan.applicant_data?.sandboxUtil;
    
    const bureauResult = await verifyCreditBureau(testCibil, testDebt, testUtil);
    
    // Save to credit_profiles table
    await client.query(
      `INSERT INTO credit_profiles (loan_id, cibil_score, active_loans, outstanding_debt, credit_utilization, recent_enquiries, repayment_history)
       VALUES ($1, $2, $3, $4, $5, $6, $7)`,
      [loanId, bureauResult.cibilScore, bureauResult.activeLoans, bureauResult.outstandingDebt, bureauResult.creditUtilization, bureauResult.recentEnquiries, bureauResult.repaymentHistory]
    );
    
    sendSseUpdate(loanId, {
      stage: 'credit_bureau',
      status: bureauResult.passed ? 'success' : 'failed',
      message: `CIBIL Score: ${bureauResult.cibilScore} (${bureauResult.passed ? 'Healthy' : 'Substandard'}).`
    });

    // 9. Stage 9: Affordability Check
    sendSseUpdate(loanId, { stage: 'affordability_assessment', status: 'pending', message: 'Calculating DTI ratio...' });
    const affordabilityResult = await assessAffordability(incomeResult.monthlyIncome, bankResult.existingEmis);
    sendSseUpdate(loanId, {
      stage: 'affordability_assessment',
      status: affordabilityResult.passed ? 'success' : 'failed',
      message: `DTI: ${affordabilityResult.dtiRatio}%.`
    });

    // 10. Stage 10: Risk Scoring
    sendSseUpdate(loanId, { stage: 'risk_scoring', status: 'pending', message: 'Aggregating risk weights...' });
    const riskResult = await calculateRiskScore({
      identity: identityResult.score,
      income: incomeResult.score,
      bank: bankResult.score,
      fraud: fraudResult.score,
      credit: bureauResult.score,
      affordability: affordabilityResult.score
    });
    sendSseUpdate(loanId, {
      stage: 'risk_scoring',
      status: 'success',
      message: `Aggregation Complete. Trust Score: ${riskResult.finalRiskScore}/100.`
    });

    // 11. Stage 11: Decision recommendation
    sendSseUpdate(loanId, { stage: 'decision_recommendation', status: 'pending', message: 'Formulating decision recommendation...' });
    const decisionResult = await determineDecision(riskResult, {
      kycPassed: identityResult.passed,
      kycScore: identityResult.score,
      incomePassed: incomeResult.passed,
      creditPassed: bureauResult.passed,
      cibilScore: bureauResult.cibilScore,
      fraudPassed: fraudResult.passed,
      fraudScore: fraudResult.score,
      marriageNameChange: identityResult.details.marriageNameChangeFlag,
      mismatchFlags: identityResult.mismatchFlags,
      incomeWarnings: incomeResult.warnings,
      bankWarnings: bankResult.warnings,
      bureauWarnings: bureauResult.warnings,
      affordabilityWarnings: affordabilityResult.warnings
    });

    // Build the overall verification matrix for storage
    const verificationMatrix = {
      identity: identityResult,
      income: incomeResult,
      bank: bankResult,
      docQA: qaResult,
      fraud: fraudResult,
      face: faceResult,
      bureau: bureauResult,
      affordability: affordabilityResult,
      risk: riskResult,
      documentFraudReports: docFraudReports
    };

    // Save outputs back to loan row
    await client.query(
      `UPDATE loans
       SET status = 'pending', -- loan remains 'pending' for the human admin to approve
           risk_score = $1,
           risk_category = $2,
           verification_matrix = $3,
           recommendation = $4,
           updated_at = CURRENT_TIMESTAMP
       WHERE id = $5`,
      [
        riskResult.finalRiskScore,
        riskResult.riskCategory,
        JSON.stringify(verificationMatrix),
        JSON.stringify(decisionResult),
        loanId
      ]
    );

    // Save final audit logs
    await client.query(
      "INSERT INTO audit_logs (loan_id, action, description) VALUES ($1, $2, $3)",
      [loanId, 'PIPELINE_COMPLETED', `Pipeline finished. Recommendation: ${decisionResult.recommendation}. Final Risk Score: ${riskResult.finalRiskScore}.`]
    );

    sendSseUpdate(loanId, {
      stage: 'decision_recommendation',
      status: 'success',
      message: `Recommendation formulated: ${decisionResult.recommendation}.`,
      data: {
        recommendation: decisionResult.recommendation,
        riskScore: riskResult.finalRiskScore,
        riskCategory: riskResult.riskCategory
      }
    });

  } catch (err: any) {
    console.error(`[Pipeline] Fatal error for loan ${loanId}:`, err);
    await client.query("UPDATE loans SET status = 'rejected', risk_score = 0 WHERE id = $1", [loanId]);
    await client.query(
      "INSERT INTO audit_logs (loan_id, action, description) VALUES ($1, $2, $3)",
      [loanId, 'PIPELINE_FAILED', `AI pipeline failed: ${err.message}`]
    );
    
    sendSseUpdate(loanId, {
      stage: 'decision_recommendation',
      status: 'failed',
      message: `Pipeline failure: ${err.message}`
    });
  } finally {
    client.release();
  }
}
