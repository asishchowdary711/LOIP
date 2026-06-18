import fs from 'fs';
import { decryptBuffer } from './crypto';

export interface MetadataValidationResult {
  isModified: boolean;
  softwareUsed: string | null;
  signaturesFound: string[];
}

/**
 * Validates the decrypted file buffer for image metadata indicating modification or AI generation.
 * Scans the binary content (using latin1 encoding to preserve bytes) for signatures and editing footprints.
 */
export function validateImageMetadata(decryptedBuffer: Buffer, fileName: string): MetadataValidationResult {
  const contentStr = decryptedBuffer.toString('latin1');
  const signaturesFound: string[] = [];
  let softwareUsed: string | null = null;

  // Skip video files
  const fileExt = fileName.split('.').pop()?.toLowerCase();
  if (fileExt === 'webm' || fileExt === 'mp4' || fileName.includes('liveness_video')) {
    return {
      isModified: false,
      softwareUsed: null,
      signaturesFound: []
    };
  }

  // 1. Photoshop checks
  if (contentStr.includes('Adobe Photoshop') || contentStr.includes('Photoshop 3.0')) {
    signaturesFound.push('Adobe Photoshop metadata signature');
    softwareUsed = 'Adobe Photoshop';
  }

  // 2. GIMP checks
  if (contentStr.includes('GIMP') || contentStr.includes('gimp')) {
    signaturesFound.push('GIMP editor signature');
    softwareUsed = 'GIMP (GNU Image Manipulation Program)';
  }

  // 3. Canva checks
  if (contentStr.includes('Canva') || contentStr.includes('canva')) {
    signaturesFound.push('Canva layout footprint');
    softwareUsed = 'Canva';
  }

  // 4. Stable Diffusion / Midjourney / DALL-E AI checks
  if (contentStr.includes('Stable Diffusion') || contentStr.includes('stablediffusion')) {
    signaturesFound.push('Stable Diffusion AI metadata signature');
    softwareUsed = 'Stable Diffusion (AI Generated)';
  }
  if (contentStr.includes('Midjourney') || contentStr.includes('midjourney')) {
    signaturesFound.push('Midjourney AI footprint');
    softwareUsed = 'Midjourney (AI Generated)';
  }
  if (contentStr.includes('DALL-E') || contentStr.includes('dalle')) {
    signaturesFound.push('DALL-E AI metadata signature');
    softwareUsed = 'DALL-E (AI Generated)';
  }

  // 5. Other general editors
  if (contentStr.includes('Paint.NET')) {
    signaturesFound.push('Paint.NET signature');
    softwareUsed = 'Paint.NET';
  }
  if (contentStr.includes('Pixlr')) {
    signaturesFound.push('Pixlr signature');
    softwareUsed = 'Pixlr Online Editor';
  }
  if (contentStr.includes('Pixelmator')) {
    signaturesFound.push('Pixelmator signature');
    softwareUsed = 'Pixelmator';
  }

  // 6. Check for EXIF Software metadata tag or XMP CreatorTool tag
  const creatorToolMatch = contentStr.match(/<xmp:CreatorTool>([^<]+)<\/xmp:CreatorTool>/i);
  if (creatorToolMatch) {
    const tool = creatorToolMatch[1].trim();
    if (!signaturesFound.includes(`Creator Tool: ${tool}`)) {
      // Ignore basic scanner and printer tools
      const lowerTool = tool.toLowerCase();
      const isScannerOrNative = lowerTool.includes('scanner') || lowerTool.includes('printer') || lowerTool.includes('scan') || lowerTool.includes('ios') || lowerTool.includes('android') || lowerTool.includes('camera');
      if (!isScannerOrNative) {
        signaturesFound.push(`Creator Tool: ${tool}`);
        if (!softwareUsed) softwareUsed = tool;
      }
    }
  }

  const producerMatch = contentStr.match(/<pdf:Producer>([^<]+)<\/pdf:Producer>/i);
  if (producerMatch) {
    const producer = producerMatch[1].trim();
    const lowerProd = producer.toLowerCase();
    // Flag if PDF was produced by designer tools rather than document scanners
    if (lowerProd.includes('photoshop') || lowerProd.includes('illustrator') || lowerProd.includes('indesign') || lowerProd.includes('gimp') || lowerProd.includes('canva')) {
      signaturesFound.push(`PDF Designer Producer: ${producer}`);
      if (!softwareUsed) softwareUsed = producer;
    }
  }

  const isModified = signaturesFound.length > 0;

  return {
    isModified,
    softwareUsed,
    signaturesFound
  };
}
