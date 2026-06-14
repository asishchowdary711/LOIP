import numpy as np
from loip.pipelines.base import BasePipeline
from schemas.decision import LoanApplication, OnboardingDecision
from loip.domains.document_intel.processor import DocumentIntelligenceProcessor
from loip.domains.identity_trust.processor import IdentityTrustProcessor
from loip.domains.income_intel.processor import IncomeIntelligenceProcessor
from loip.domains.affordability.processor import AffordabilityProcessor
from loip.domains.risk_decisioning.processor import RiskDecisionProcessor
from loip.domains.fraud.processor import FraudIntelligenceProcessor
from loip.domains.explainability.processor import ExplainabilityProcessor
from loip.domains.human_review.processor import ReviewProcessor
from integrations.cibil_client import CIBILClient

class OnboardingPipeline(BasePipeline):
    def __init__(self, mock_mode: bool = True):
        self.doc_processor = DocumentIntelligenceProcessor(mock_mode=mock_mode)
        self.identity_processor = IdentityTrustProcessor(mock_mode=mock_mode)
        self.income_processor = IncomeIntelligenceProcessor(mock_mode=mock_mode)
        self.affordability_processor = AffordabilityProcessor(mock_mode=mock_mode)
        self.fraud_processor = FraudIntelligenceProcessor(mock_mode=mock_mode)
        self.decision_processor = RiskDecisionProcessor(mock_mode=mock_mode)
        self.explainability_processor = ExplainabilityProcessor(mock_mode=mock_mode)
        self.review_processor = ReviewProcessor(mock_mode=mock_mode)
        self.cibil_client = CIBILClient()
        self.cibil_client._mock = mock_mode

    async def execute(self, application: LoanApplication, images: list[np.ndarray], application_data: dict, raw_documents: list[bytes] | None = None, document_store=None, event_publisher=None, identity_graph=None, vcip=None) -> OnboardingDecision:
        from loip.events import Topic

        app_id = application.application_id

        async def emit(topic: str, payload: dict) -> None:
            if event_publisher is not None:
                await event_publisher.publish(topic, key=app_id, payload={"application_id": app_id, **payload})

        # PDF-rendered document classes vs. image-based ones (for storage ext).
        pdf_doc_classes = {"salary_slip", "bank_statement", "itr", "form16", "gst_return"}
        extracted_data = {}
        document_ids: dict[str, str] = {}
        for i, img in enumerate(images):
            doc_result = self.doc_processor.process(img)
            doc_class = doc_result["classification"].document_class.value
            fields = {}
            for f in doc_result["extraction"].fields:
                fields[f.name] = f.value
            extracted_data[doc_class] = fields

            # Persist the source document to MinIO and record its id so
            # document-derived evidence can trace back to a real object.
            if document_store is not None and raw_documents is not None and i < len(raw_documents):
                ext = "pdf" if doc_class in pdf_doc_classes else "png"
                document_ids[doc_class] = document_store.store(doc_class, raw_documents[i], ext=ext)

        await emit(Topic.DOCUMENT_CLASSIFIED, {"document_classes": list(extracted_data.keys())})

        selfie_img = images[-1] if len(images) > 1 else None
        doc_face_img = images[0] if images else None

        identity_result = await self.identity_processor.verify_identity(
            application.application_id,
            {**extracted_data.get("pan", {}), **extracted_data.get("aadhaar", {}), **extracted_data.get("passport", {})},
            application_data,
            selfie_img=selfie_img,
            doc_face_img=doc_face_img
        )
        await emit(Topic.IDENTITY_VERIFIED, {
            "identity_confidence": identity_result.identity_confidence,
            "tamper_flags": list(identity_result.tamper_flags),
        })

        income_result = self.income_processor.process_income(
            application.application_id,
            extracted_data,
            segment=application.employment_type,
            application_employer_name=application.employer_name,
            document_ids=document_ids,
        )
        await emit(Topic.INCOME_RECONCILED, {
            "verified_monthly_income": income_result.verified_monthly_income,
            "income_confidence": income_result.income_confidence,
        })

        affordability_result = self.affordability_processor.process_affordability(
            application.application_id,
            income_result.model_dump(),
            application.model_dump(),
            extracted_data
        )
        await emit(Topic.AFFORDABILITY_COMPUTED, {
            "foir": affordability_result.foir,
            "disposable_income": affordability_result.disposable_income,
        })

        bureau_result = await self.cibil_client.fetch_report(
            pan=extracted_data.get("pan", {}).get("pan_number", ""),
            dob=extracted_data.get("pan", {}).get("date_of_birth", ""),
            name=extracted_data.get("pan", {}).get("full_name", ""),
            application_id=application.application_id,
            consent_verified=True
        )
        await emit(Topic.CONSENT_CAPTURED, {"purpose": "credit_bureau_pull", "cibil_score": bureau_result.score})

        fraud_result = self.fraud_processor.process_fraud(
            application.application_id,
            identity_result.model_dump(),
            extracted_data,
            application_data,
            identity_graph=identity_graph,
        )
        await emit(Topic.FRAUD_SCORED, {"fraud_score": fraud_result.fraud_score})

        decision = self.decision_processor.decide(
            application,
            identity_result,
            income_result,
            affordability_result,
            bureau_result,
            fraud_result,
            vcip=vcip,
        )
        decision.fraud_result = fraud_result

        risk_features = {
            "identity_confidence": identity_result.identity_confidence,
            "income_confidence": income_result.income_confidence,
            "foir": affordability_result.foir,
            "cibil_score_normalized": max(0.0, (bureau_result.score - 300) / 600),
            "cashflow_stability": affordability_result.cashflow_stability,
            "employment_tier": application.employment_tier,
            "loan_to_income_ratio": application.loan_amount / max(1, (income_result.verified_monthly_income * 12)),
        }

        case_data = {
            "application": application.model_dump(),
            "identity": identity_result.model_dump(),
            "income": income_result.model_dump(),
            "affordability": affordability_result.model_dump(),
            "bureau": bureau_result.model_dump(),
            "decision": decision.model_dump(),
        }

        explainability_result = await self.explainability_processor.explain(
            application_id=application.application_id,
            risk_features=risk_features,
            case_data=case_data,
        )

        decision.risk_factors = explainability_result.risk_factors
        if explainability_result.copilot:
            decision.copilot_narrative = explainability_result.copilot.profile_summary

        from loip.web.routes.audit import store_explainability
        store_explainability(application.application_id, explainability_result)

        await emit(Topic.RISK_DECIDED, {
            "decision": decision.decision.value,
            "risk_score": decision.risk_score,
            "reason_codes": [rc.code for rc in decision.reason_codes],
        })

        if decision.decision.value in ("review", "reject"):
            self.review_processor.create_review_case(decision)
            await emit(Topic.REVIEW_ASSIGNED, {"decision": decision.decision.value})

        return decision
