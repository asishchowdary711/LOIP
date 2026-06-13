import numpy as np
from loip.domains.document_intel.schemas import ExtractionResult, ExtractionField, DocumentClass

class Qwen25VLWrapper:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        
    def extract_fields(self, image: np.ndarray, doc_class: DocumentClass) -> ExtractionResult:
        if self.mock_mode:
            fields = []
            if doc_class == DocumentClass.SALARY_SLIP:
                fields = [
                    ExtractionField(name="employer_name", value="Acme Corp", confidence=0.95),
                    ExtractionField(name="net_pay", value="50000", confidence=0.98),
                ]
            elif doc_class == DocumentClass.PAN:
                fields = [
                    ExtractionField(name="pan_number", value="ABCDE1234F", confidence=0.99),
                    ExtractionField(name="full_name", value="Mock User", confidence=0.99),
                    ExtractionField(name="date_of_birth", value="01/01/1990", confidence=0.99),
                ]
            elif doc_class == DocumentClass.AADHAAR:
                fields = [
                    ExtractionField(name="aadhaar_number", value="123456789012", confidence=0.99),
                ]
            elif doc_class == DocumentClass.ITR:
                fields = [
                    ExtractionField(name="total_income", value="800000", confidence=0.95),
                ]
            elif doc_class == DocumentClass.GST_RETURN:
                fields = [
                    ExtractionField(name="turnover_b2b", value="5000000", confidence=0.90),
                    ExtractionField(name="turnover_b2c", value="1000000", confidence=0.90),
                ]
            return ExtractionResult(
                document_class=doc_class,
                fields=fields,
                model="qwen2.5-vl",
                overall_confidence=0.96
            )
        return ExtractionResult(document_class=doc_class, fields=[], model="qwen2.5-vl", overall_confidence=0.0)
