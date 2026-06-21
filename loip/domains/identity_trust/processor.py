from loip.models.bge_m3_wrapper import BGEM3Wrapper
from loip.models.arcface_wrapper import ArcFaceWrapper
from loip.models.minifasnet_wrapper import MiniFASNetWrapper
from loip.integrations.nsdl_client import NSDLClient
from loip.integrations.uidai_client import UIDAIClient
from loip.schemas.identity import (
    IdentityVerificationResult, EntityMatch, APIVerificationResult, IdentityFlag
)
from loip.domains.qr_trust.processor import QRTrustProcessor
from loip.domains.qr_trust.schemas import QRTrustFlag


class IdentityTrustProcessor:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self.bge_m3 = BGEM3Wrapper(mock_mode=mock_mode)
        self.arcface = ArcFaceWrapper(mock_mode=mock_mode)
        self.minifasnet = MiniFASNetWrapper(mock_mode=mock_mode)
        self.nsdl_client = NSDLClient()
        self.nsdl_client._mock = mock_mode
        self.uidai_client = UIDAIClient()
        self.uidai_client._mock = mock_mode
        self.qr_trust_processor = QRTrustProcessor(mock_mode=mock_mode)

    async def verify_identity(
        self,
        application_id: str,
        extracted_fields: dict,
        application_data: dict,
        selfie_img=None,
        doc_face_img=None,
        document_metadata: dict | None = None,
        qr_results: dict | None = None,
        source_image_bytes: dict | None = None,
        images_by_class: dict | None = None,
        extracted_by_class: dict | None = None,
    ) -> IdentityVerificationResult:
        result = IdentityVerificationResult(application_id=application_id, identity_confidence=1.0)
        
        # 1. API Verification
        if "pan_number" in extracted_fields and "full_name" in extracted_fields and "date_of_birth" in extracted_fields:
            nsdl_res = await self.nsdl_client.verify_pan(
                pan_number=extracted_fields["pan_number"],
                full_name=extracted_fields["full_name"],
                dob=extracted_fields["date_of_birth"]
            )
            result.api_results.append(nsdl_res)
            result.pan_verified = nsdl_res.matched
            if not nsdl_res.matched:
                if nsdl_res.status == "format_invalid":
                    result.tamper_flags.append(IdentityFlag.PAN_FORMAT_INVALID)
                else:
                    result.tamper_flags.append(IdentityFlag.PAN_NSDL_INACTIVE)
                    
        # Aadhaar Verhoeff checksum (build-plan rule: aadhaar_format_invalid).
        if "aadhaar_number" in extracted_fields:
            from loip.validation import is_valid_aadhaar
            if not is_valid_aadhaar(extracted_fields["aadhaar_number"]):
                result.tamper_flags.append(IdentityFlag.AADHAAR_FORMAT_INVALID)
                result.mismatches.append("Aadhaar number fails Verhoeff checksum / format")

        if "aadhaar_number" in extracted_fields and "aadhaar_otp" in application_data:
            uidai_res = await self.uidai_client.verify_otp(
                aadhaar_number=extracted_fields["aadhaar_number"],
                otp=application_data["aadhaar_otp"],
                txn_id="mock-txn-id",
                consent_verified=True
            )
            result.api_results.append(uidai_res)
            result.aadhaar_verified = uidai_res.matched
            if not uidai_res.matched:
                result.tamper_flags.append(IdentityFlag.AADHAAR_OTP_FAILED)

        # 2. Face Verification & Liveness
        if selfie_img is not None:
            liveness = self.minifasnet.detect_liveness(selfie_img)
            result.liveness_score = liveness
            result.liveness_verified = liveness >= 0.50
            if not result.liveness_verified:
                result.tamper_flags.append(IdentityFlag.SPOOF_DETECTED)
                
            if doc_face_img is not None:
                sim = self.arcface.verify_face(selfie_img, doc_face_img)
                result.face_match_score = sim
                result.face_verified = sim >= 0.60
                if not result.face_verified:
                    result.tamper_flags.append(IdentityFlag.FACE_MISMATCH)

        # 3. Cross-check Names (PAN vs Aadhaar vs App) — semantic match via BGE-M3.
        # Compare each document's name against the application form name, and
        # PAN vs Aadhaar against each other. Mismatch raises a single flag once.
        name_pairs: list[tuple[str, str, str]] = []  # (field_name, a, b)
        app_name = application_data.get("full_name")
        pan_name = (extracted_by_class or {}).get("pan", {}).get("full_name")
        aadhaar_name = (extracted_by_class or {}).get("aadhaar", {}).get("full_name")
        # Fallback to merged dict when per-class breakdown not supplied.
        if pan_name is None and aadhaar_name is None and "full_name" in extracted_fields:
            pan_name = extracted_fields["full_name"]

        if pan_name and app_name:
            name_pairs.append(("full_name_pan_vs_app", pan_name, app_name))
        if aadhaar_name and app_name:
            name_pairs.append(("full_name_aadhaar_vs_app", aadhaar_name, app_name))
        if pan_name and aadhaar_name:
            name_pairs.append(("full_name_pan_vs_aadhaar", pan_name, aadhaar_name))

        any_name_mismatch = False
        for field_name, a, b in name_pairs:
            sim = self.bge_m3.similarity(a, b)
            match = EntityMatch(
                field_name=field_name,
                sources=[],
                similarity_score=sim,
                threshold=0.85,
                passed=sim >= 0.85,
            )
            result.entity_matches.append(match)
            if not match.passed:
                any_name_mismatch = True
                result.mismatches.append(
                    f"Name similarity {sim:.2f} below 0.85 for {field_name} ('{a}' vs '{b}')"
                )
        if any_name_mismatch:
            result.tamper_flags.append(IdentityFlag.NAME_PAN_AADHAAR_MISMATCH)
                
        # DOB match
        dob_sources = []
        if "date_of_birth" in extracted_fields:
            dob_sources.append(extracted_fields["date_of_birth"])
        if "date_of_birth" in application_data:
            dob_sources.append(application_data["date_of_birth"])
            
        if len(dob_sources) >= 2:
            if dob_sources[0] != dob_sources[1]:
                result.tamper_flags.append(IdentityFlag.DOB_MISMATCH)
                result.mismatches.append("DOB mismatch between documents/application")

        # 4. Document metadata tamper check (e.g. PDF edited in Photoshop)
        if document_metadata:
            producer_info = f"{document_metadata.get('producer', '')} {document_metadata.get('creator', '')}".lower()
            if "photoshop" in producer_info:
                result.tamper_flags.append(IdentityFlag.DOCUMENT_METADATA_ANOMALY)
                result.mismatches.append("Document metadata indicates editing software (possible tamper)")

        # 5. QR Trust Verification
        if qr_results is not None:
            qr_trust_result = self.qr_trust_processor.verify(
                application_id=application_id,
                qr_decode_results=qr_results,
                extracted_fields=extracted_fields,
                source_image_bytes=source_image_bytes,
                images_by_class=images_by_class,
            )
            result.qr_trust_result = qr_trust_result

            if qr_trust_result.has_flag(QRTrustFlag.QR_SIGNATURE_INVALID):
                result.tamper_flags.append(IdentityFlag.QR_SIGNATURE_INVALID)
                result.mismatches.append("Aadhaar QR digital signature invalid")
            if any(qr_trust_result.has_flag(f) for f in (
                QRTrustFlag.QR_NAME_MISMATCH,
                QRTrustFlag.QR_DOB_MISMATCH,
                QRTrustFlag.QR_ID_NUMBER_MISMATCH,
            )):
                result.tamper_flags.append(IdentityFlag.QR_DATA_MISMATCH)
                result.mismatches.append("QR data does not match OCR-extracted fields")
            if qr_trust_result.has_flag(QRTrustFlag.QR_TAMPERED):
                result.tamper_flags.append(IdentityFlag.QR_TAMPERED)
                result.mismatches.append("Document image shows signs of tampering (ELA + EXIF)")

        # Confidence heuristic
        score = 1.0
        if not result.pan_verified: score -= 0.3
        if not result.aadhaar_verified: score -= 0.3
        if selfie_img is not None and not result.face_verified: score -= 0.3
        if result.tamper_flags: score -= 0.2 * len(result.tamper_flags)
        if result.qr_trust_result is not None:
            score -= (1.0 - result.qr_trust_result.trust_score) * 0.25

        result.identity_confidence = max(0.0, min(1.0, score))

        result.evidence_chains = [r.evidence for r in result.api_results if r.evidence is not None]

        return result
