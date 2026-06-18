import path from 'path';
import { DocumentFraudReport } from '../engines/documentFraudExpert';

/**
 * Calls the real Google Gemini Multimodal Vision API (gemini-2.5-flash) via native fetch
 * to visually inspect the document image/PDF for photoshop editing, AI generation, and tampering.
 */
export async function analyzeDocumentWithGemini(
  decryptedBuffer: Buffer,
  filePath: string,
  docType: string,
  applicantName: string
): Promise<DocumentFraudReport | null> {
  const apiKey = process.env.GEMINI_API_KEY;
  const openrouterKey = process.env.OPENROUTER_API_KEY;

  if (!apiKey && !openrouterKey) {
    // Graceful fallback to offline engine
    return null;
  }

  // Determine mimeType
  const ext = path.extname(filePath).replace('.enc', '').toLowerCase();
  let mimeType = 'image/jpeg';
  if (ext === '.png') mimeType = 'image/png';
  else if (ext === '.pdf') mimeType = 'application/pdf';
  else if (ext === '.txt') mimeType = 'text/plain';

  const base64Data = decryptedBuffer.toString('base64');

  const promptText = `
You are an AI document fraud detection expert.
Analyze the provided document file and determine whether it appears authentic, edited, manipulated, forged, AI-generated, or suspicious.
The applicant's declared name is: "${applicantName}".

Perform the following checks:
1. Document Quality:
   - Check image clarity, blur, cropping, and resolution.
   - Identify excessive compression artifacts.
2. Text Consistency:
   - Detect font inconsistencies.
   - Check for uneven character spacing.
   - Identify overwritten or modified text.
   - Verify alignment of text fields.
3. Image Manipulation Detection:
   - Look for cut-and-paste regions.
   - Detect cloned areas.
   - Detect background inconsistencies.
   - Identify signs of Photoshop or image editing.
   - Detect altered dates, names, document numbers, or addresses.
4. Security Features:
   - Verify presence of expected logos, seals, emblems, and watermarks.
   - Detect missing or distorted security elements.
5. QR Code Analysis:
   - Determine whether a QR code exists.
   - Verify whether the QR code appears damaged, manipulated, or unreadable.
6. Layout Validation:
   - Compare document layout against known Aadhaar, PAN, or Voter ID structures.
   - Detect misplaced elements or unusual formatting.
7. AI Generated Content Detection:
   - Identify signs of synthetic images.
   - Detect GAN artifacts.
   - Detect unrealistic text rendering.
   - Detect inconsistent shadows, borders, or textures.
8. Fraud Indicators:
   - Highlight all suspicious regions.
   - Explain why they appear suspicious.

Provide output strictly in JSON format matching this schema:
{
  "documentType": "${docType}",
  "isFake": false,
  "confidenceScore": 0,
  "riskLevel": "LOW|MEDIUM|HIGH",
  "tamperingDetected": false,
  "suspectedEdits": [
    {
      "field": "name | dob | photo | metadata | etc",
      "reason": "Description of why this looks edited/suspicious",
      "confidence": 95
    }
  ],
  "securityFeatureStatus": {
    "logoPresent": true,
    "watermarkPresent": true,
    "qrCodePresent": true,
    "qrCodeSuspicious": false
  },
  "observations": ["Detail 1", "Detail 2"],
  "recommendation": "APPROVE|MANUAL_REVIEW|REJECT"
}

Important:
- Never assume a document is genuine. If there are visible signs of copy-paste, text overlay, or metadata tampering, flag it.
- If confidence score is below 70%, recommend MANUAL_REVIEW.
- Return raw JSON only, no markdown wrapping, no explanation outside the JSON.
`;

  try {
    let responseText = '';

    if (apiKey) {
      console.log(`[Gemini API] Requesting visual analysis for ${docType} (${mimeType}) directly...`);
      const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`;
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [
            {
              parts: [
                { text: promptText },
                { inlineData: { mimeType, data: base64Data } }
              ]
            }
          ],
          generationConfig: { responseMimeType: 'application/json' }
        })
      });

      if (!response.ok) {
        const errBody = await response.text();
        throw new Error(`Gemini API responded with status ${response.status}: ${errBody}`);
      }

      const data = (await response.json()) as any;
      responseText = data?.candidates?.[0]?.content?.parts?.[0]?.text || '';
    } else if (openrouterKey) {
      console.log(`[OpenRouter API] Requesting visual analysis for ${docType} (${mimeType}) via OpenRouter...`);
      const url = 'https://openrouter.ai/api/v1/chat/completions';
      const model = process.env.OPENROUTER_MODEL || 'google/gemini-2.5-flash';
      
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${openrouterKey}`,
          'HTTP-Referer': 'https://digital-loan.com',
          'X-Title': 'Digital Loan Platform'
        },
        body: JSON.stringify({
          model,
          messages: [
            {
              role: 'user',
              content: [
                { type: 'text', text: promptText },
                {
                  type: 'image_url',
                  image_url: { url: `data:${mimeType};base64,${base64Data}` }
                }
              ]
            }
          ],
          response_format: { type: 'json_object' }
        })
      });

      if (!response.ok) {
        const errBody = await response.text();
        throw new Error(`OpenRouter API responded with status ${response.status}: ${errBody}`);
      }

      const data = (await response.json()) as any;
      responseText = data?.choices?.[0]?.message?.content || '';
    }

    if (responseText) {
      // Parse structured JSON
      const parsedReport = JSON.parse(responseText.trim()) as DocumentFraudReport;
      console.log(`[Visual AI Engine] Visual analysis successfully completed for ${docType}. Tampering detected: ${parsedReport.tamperingDetected}`);
      return parsedReport;
    }

    throw new Error('Empty response from AI visual verification API');
  } catch (err: any) {
    console.warn(`[Visual AI Engine Error] Failed calling visual inspection for ${docType}:`, err.message);
    // Returning null signals the caller to use local offline heuristics fallback
    return null;
  }
}
