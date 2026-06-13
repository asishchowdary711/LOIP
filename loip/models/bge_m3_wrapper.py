class BGEM3Wrapper:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self.model = None
        if not self.mock_mode:
            try:
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer('BAAI/bge-m3')
            except ImportError:
                self.mock_mode = True

    def similarity(self, text1: str, text2: str) -> float:
        if self.mock_mode:
            if text1.lower() == text2.lower(): return 1.0
            if text1.lower() in text2.lower() or text2.lower() in text1.lower(): return 0.85
            return 0.5
            
        embeddings = self.model.encode([text1, text2])
        sim = (embeddings[0] @ embeddings[1].T) / (
            (embeddings[0] ** 2).sum() ** 0.5 * (embeddings[1] ** 2).sum() ** 0.5
        )
        return float(sim)
