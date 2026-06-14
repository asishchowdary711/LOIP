from loip.models.bge_m3_wrapper import BGEM3Wrapper
from loip.models.arcface_wrapper import ArcFaceWrapper
from loip.models.minifasnet_wrapper import MiniFASNetWrapper
from integrations.nsdl_client import NSDLClient
from integrations.uidai_client import UIDAIClient
from schemas.identity import (
    IdentityVerificationResult, EntityMatch, APIVerificationResult, IdentityFlag
)

class IdentityTrustProcessor:
    def __init__(self, mock_mode: bool = True):
        self.bge_m3 = BGEM3Wrapper(mock_mode=mock_mode)
        self.arcface = ArcFaceWrapper(mock_mode=mock_mode)
        self.minifasnet = MiniFASNetWrapper(mock_mode=mock_mode)
        self.nsdl_client = NSDLClient()
        self.nsdl_client._mock = mock_mode
        self.uidai_client = UIDAIClient()
        self.uidai_client._mock = mock_mode

    async def verify_identity(self, application_id: str, extracted_fields: dict, application_data: dict, selfie_img=None, doc_face_img=None, document_metadata: dict | None = None) -> IdentityVerificationResult:
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

        # 3. Cross-check Names (PAN vs Aadhaar vs App)
        name_sources = []
        if "full_name" in extracted_fields:
            name_sources.append(extracted_fields["full_name"])
        if "full_name" in application_data:
            name_sources.append(application_data["full_name"])
            
        if len(name_sources) >= 2:
            sim = self.bge_m3.similarity(name_sources[0], name_sources[1])
            match = EntityMatch(
                field_name="full_name",
                sources=[],
                similarity_score=sim,
                threshold=0.85,
                passed=sim >= 0.85
            )
            result.entity_matches.append(match)
            if not match.passed:
                result.tamper_flags.append(IdentityFlag.NAME_PAN_AADHAAR_MISMATCH)
                result.mismatches.append("Name mismatch between documents/application")
                
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

        # Confidence heuristic
        score = 1.0
        if not result.pan_verified: score -= 0.3
        if not result.aadhaar_verified: score -= 0.3
        if selfie_img is not None and not result.face_verified: score -= 0.3
        if result.tamper_flags: score -= 0.2 * len(result.tamper_flags)
        
        result.identity_confidence = max(0.0, min(1.0, score))

        result.evidence_chains = [r.evidence for r in result.api_results if r.evidence is not None]

        return result
