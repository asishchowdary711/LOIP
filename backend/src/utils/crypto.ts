import crypto from 'crypto';
import dotenv from 'dotenv';

dotenv.config();

const ALGORITHM = 'aes-256-cbc';
const IV_LENGTH = 16; // AES block size is 16 bytes

// Load encryption key from environment. Fallback to a generated key for safety if undefined.
const getEncryptionKey = (): Buffer => {
  const hexKey = process.env.ENCRYPTION_KEY;
  if (!hexKey || hexKey.length !== 64) {
    console.warn('WARNING: ENCRYPTION_KEY is missing or invalid in .env! Generating a temporary session key.');
    // Generate a temporary 32-byte key
    return crypto.randomBytes(32);
  }
  return Buffer.from(hexKey, 'hex');
};

/**
 * Encrypts a raw buffer using AES-256-CBC.
 * The 16-byte random IV is prepended to the final encrypted buffer.
 */
export function encryptBuffer(data: Buffer): Buffer {
  const key = getEncryptionKey();
  const iv = crypto.randomBytes(IV_LENGTH);
  
  const cipher = crypto.createCipheriv(ALGORITHM, key, iv);
  const encrypted = Buffer.concat([cipher.update(data), cipher.final()]);
  
  // Return IV + Encrypted Data
  return Buffer.concat([iv, encrypted]);
}

/**
 * Decrypts a buffer that has a 16-byte IV prepended.
 */
export function decryptBuffer(encryptedWithIv: Buffer): Buffer {
  const key = getEncryptionKey();
  
  // Extract IV (first 16 bytes) and ciphertext (rest)
  const iv = encryptedWithIv.subarray(0, IV_LENGTH);
  const ciphertext = encryptedWithIv.subarray(IV_LENGTH);
  
  const decipher = crypto.createDecipheriv(ALGORITHM, key, iv);
  return Buffer.concat([decipher.update(ciphertext), decipher.final()]);
}
