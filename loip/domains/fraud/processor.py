import logging

from loip.models.graphsage_wrapper import GraphSAGEWrapper
from loip.validation import validate_mrz_td3
from loip.schemas.evidence import EvidenceChain, ReconciliationMethod
from loip.schemas.fraud import FraudResult, FraudSignal, FraudSignalType

logger = logging.getLogger(__name__)


def _graph_attributes(extracted_data: dict, application_data: dict) -> dict[str, str]:
    """Pull identity-graph node attributes from extracted + application data."""
    pan = extracted_data.get("pan", {}).get("pan_number") \
        or extracted_data.get("salary_slip", {}).get("employee_pan", "")
    return {
        "pan": pan or "",
        "aadhaar": extracted_data.get("aadhaar", {}).get("aadhaar_number", ""),
        "phone": application_data.get("phone") or application_data.get("mobile", ""),
        "email": application_data.get("email", ""),
        "device": application_data.get("device_id") or application_data.get("device_fingerprint", ""),
        "employer": application_data.get("employer_name")
        or extracted_data.get("salary_slip", {}).get("employer_name", ""),
        "bank_account": extracted_data.get("bank_statement", {}).get("account_number", ""),
        "address": extracted_data.get("aadhaar", {}).get("address")
        or application_data.get("address", ""),
    }


class FraudIntelligenceProcessor:
    def __init__(self, mock_mode: bool = True):
        self.graphsage = GraphSAGEWrapper(mock_mode=mock_mode)

    def process_fraud(self, application_id: str, identity_result: dict, extracted_data: dict, application_data: dict, identity_graph=None) -> FraudResult:
        result = FraudResult(application_id=application_id, fraud_score=0.0)

        # 1. Document Forgery Hard Rules
        # E.g. Check for tampered metadata, known spoof cases
        if identity_result.get("liveness_score") is not None and identity_result.get("liveness_verified") is False:
            result.signals.append(FraudSignal(
                signal_type=FraudSignalType.DOCUMENT_FORGERY,
                severity=0.9,
                description="Liveness detection failed, possible spoof",
                evidence=EvidenceChain(
                    claim="liveness_score < threshold",
                    supporting=[],
                    reconciled_value="spoof",
                    reconciliation_method=ReconciliationMethod.HIGHEST_CONFIDENCE,
                    confidence=0.98
                )
            ))

        # 2. Passport MRZ checksum (ICAO 9303) — document forgery rule.
        mrz_line2 = extracted_data.get("passport", {}).get("mrz_line2")
        if mrz_line2 and not validate_mrz_td3(mrz_line2):
            result.signals.append(FraudSignal(
                signal_type=FraudSignalType.DOCUMENT_FORGERY,
                severity=0.9,
                description="Passport MRZ check digits fail ICAO 9303 validation",
                evidence=EvidenceChain(
                    claim="mrz_checksum_invalid",
                    supporting=[],
                    reconciled_value="forged_passport",
                    reconciliation_method=ReconciliationMethod.HIGHEST_CONFIDENCE,
                    confidence=0.95,
                ),
            ))

        # 3. Neo4j identity-graph fraud rings (pan_farming, synthetic-identity,
        #    address rings). Best-effort: skipped if Neo4j is unavailable.
        if identity_graph is not None:
            try:
                identity_graph.ingest_application(
                    application_id, _graph_attributes(extracted_data, application_data)
                )
                for sig in identity_graph.detect_fraud_rings(application_id):
                    result.signals.append(FraudSignal(
                        signal_type=FraudSignalType(sig["signal_type"]),
                        severity=sig["severity"],
                        description=sig["description"],
                        evidence=EvidenceChain(
                            claim=sig["signal_type"],
                            supporting=[],
                            reconciled_value=",".join(sig.get("peers", [])) or "ring_detected",
                            reconciliation_method=ReconciliationMethod.COMPUTED,
                            confidence=sig["severity"],
                        ),
                    ))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Identity-graph fraud check failed for %s: %s", application_id, exc)

        # 4. GraphSAGE Anomaly
        # We build node features from current app + context
        node_features = {
            "pan": extracted_data.get("pan", {}).get("pan_number", ""),
            "aadhaar": extracted_data.get("aadhaar", {}).get("aadhaar_number", "")
        }
        graph_fraud_score = self.graphsage.predict_fraud(node_features, {"application_id": application_id})
        result.graph_fraud_score = graph_fraud_score

        if graph_fraud_score > 0.8:
            result.signals.append(FraudSignal(
                signal_type=FraudSignalType.SYNTHETIC_IDENTITY_RING,
                severity=graph_fraud_score,
                description="High graph anomaly score, applicant might be part of a synthetic ring",
                evidence=EvidenceChain(
                    claim=f"graph_fraud_score = {graph_fraud_score}",
                    supporting=[],
                    reconciled_value="fraud_ring_detected",
                    reconciliation_method=ReconciliationMethod.COMPUTED,
                    confidence=graph_fraud_score
                )
            ))

        # Final fraud score computation (simple max of severities)
        if result.signals:
            result.fraud_score = max(s.severity for s in result.signals)

        result.evidence_chains = [s.evidence for s in result.signals]

        return result
