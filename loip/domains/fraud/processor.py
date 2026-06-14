from loip.models.graphsage_wrapper import GraphSAGEWrapper
from schemas.fraud import FraudResult, FraudSignal, FraudSignalType
from schemas.evidence import EvidenceChain, ReconciliationMethod

class FraudIntelligenceProcessor:
    def __init__(self, mock_mode: bool = True):
        self.graphsage = GraphSAGEWrapper(mock_mode=mock_mode)

    def process_fraud(self, application_id: str, identity_result: dict, extracted_data: dict, application_data: dict) -> FraudResult:
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
            
        # 2. GraphSAGE Anomaly
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
