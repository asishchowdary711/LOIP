from loip.domains.document_intel.schemas import DocumentClass
from scripts.evaluate_qwen_docvqa import QAPair, evaluate, normalized_similarity, question_score


def test_normalized_similarity_exact_match_is_one():
    assert normalized_similarity("ABCDE1234F", "ABCDE1234F") == 1.0


def test_normalized_similarity_case_and_whitespace_insensitive():
    assert normalized_similarity(" abcde1234f ", "ABCDE1234F") == 1.0


def test_normalized_similarity_large_edit_distance_clamps_to_zero():
    assert normalized_similarity("completely different", "ABCDE1234F") == 0.0


def test_question_score_takes_best_of_multiple_ground_truths():
    assert question_score("Wipro", ["TCS", "Wipro", "Infosys"]) == 1.0


def test_evaluate_perfect_predictions_gives_anls_one():
    qa_pairs = [
        QAPair(image_path="x.png", document_class=DocumentClass.PAN, question="What is the PAN number?", answers=["ABCDE1234F"]),
        QAPair(image_path="y.png", document_class=DocumentClass.SALARY_SLIP, question="What is the employer name?", answers=["Wipro"]),
    ]
    predictions = ["ABCDE1234F", "Wipro"]

    assert evaluate(qa_pairs, predictions) == 1.0


def test_evaluate_mixed_predictions_averages_scores():
    qa_pairs = [
        QAPair(image_path="x.png", document_class=DocumentClass.PAN, question="What is the PAN number?", answers=["ABCDE1234F"]),
        QAPair(image_path="y.png", document_class=DocumentClass.SALARY_SLIP, question="What is the employer name?", answers=["Wipro"]),
    ]
    predictions = ["ABCDE1234F", "completely wrong answer"]

    anls = evaluate(qa_pairs, predictions)
    assert 0.0 < anls < 1.0
    assert anls == 0.5
