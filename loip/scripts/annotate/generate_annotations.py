"""Generator JSON + document image → LayoutLMv3 BIO annotations + Donut GT.

Input:
  - document_image: PNG/PDF rendered by a generator
  - generator_metadata: JSON with ground-truth field values

Output (per document):
  - layoutlmv3_annotation.json → FUNSD-format with normalized bboxes (0-1000)
  - donut_annotation.json      → { "gt_parse": { field: value, ... } }
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import click
from PIL import Image

from .label_schema import (
    ADDRESS_LABELS,
    BANK_STATEMENT_TXN_LABELS,
    LABEL_SCHEMAS,
    get_bio_labels,
)

logger = logging.getLogger(__name__)

try:
    from paddleocr import PaddleOCR
except ImportError:
    PaddleOCR = None


def _init_ocr() -> PaddleOCR:
    if PaddleOCR is None:
        raise ImportError(
            "paddleocr is required for annotation generation. "
            "Install with: pip install paddleocr"
        )
    return PaddleOCR(use_textline_orientation=True, lang="en")


def _normalize_bbox(
    bbox: list[list[float]], img_width: int, img_height: int
) -> list[int]:
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return [
        int(min(xs) / img_width * 1000),
        int(min(ys) / img_height * 1000),
        int(max(xs) / img_width * 1000),
        int(max(ys) / img_height * 1000),
    ]


def _split_line_into_word_tokens(
    text: str, line_bbox: list[int], confidence: float
) -> list[dict]:
    """Split a PaddleOCR line-level result into word tokens with estimated bboxes.

    PaddleOCR returns one bbox per recognized line, but ground-truth field
    matching is done at the word/phrase level, so each line is split on
    whitespace and its bbox divided proportionally by character width.
    """
    words = text.split()
    if not words:
        return []

    x0, y0, x1, y1 = line_bbox
    total_chars = sum(len(w) for w in words)
    width = x1 - x0
    tokens = []
    cursor = x0
    for word in words:
        word_width = round(width * len(word) / total_chars) if total_chars else 0
        tokens.append({
            "text": word,
            "bbox": [cursor, y0, cursor + word_width, y1],
            "confidence": confidence,
            "label": "O",
        })
        cursor += word_width
    return tokens


def _fuzzy_match(ocr_text: str, gt_value: str, exact: bool = False) -> bool:
    ocr_clean = ocr_text.strip().upper().replace(",", "").replace("₹", "").replace(":", "")
    gt_clean = str(gt_value).strip().upper().replace(",", "").replace("₹", "")
    if not ocr_clean or not gt_clean:
        return False
    if exact:
        return ocr_clean == gt_clean
    if ocr_clean == gt_clean:
        return True
    if len(gt_clean) < 3:
        return ocr_clean == gt_clean
    dist = _levenshtein(ocr_clean, gt_clean)
    return dist <= 2


def _levenshtein(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[len(s2)]


def _is_exact_field(field_name: str) -> bool:
    exact_patterns = {
        "pan_number", "aadhaar_number", "account_number", "employee_pan",
        "employer_tan", "gstin", "uan", "pincode",
    }
    return field_name in exact_patterns


def _is_numeric_field(field_name: str) -> bool:
    numeric_patterns = {
        "gross_pay", "net_pay", "basic", "hra", "pf_deduction", "tds_deduction",
        "opening_balance", "closing_balance", "gross_salary", "taxable_income",
        "tds_deducted", "gross_total_income", "total_tax_paid",
        "total_taxable_value", "total_tax_payable",
        "pay_year", "assessment_year",
    }
    return field_name in numeric_patterns


def _tokenize_value(value: str) -> list[str]:
    return str(value).split()


def _build_gt_lookup(
    metadata: dict, doc_type: str
) -> list[tuple[str, str, list[str]]]:
    """Returns list of (field_name, bio_tag, value_tokens) for matching."""
    schema = LABEL_SCHEMAS.get(doc_type, {})
    entries = []

    for field_name, bio_tag in schema.items():
        value = metadata.get(field_name)
        if value is None or value == "":
            continue
        tokens = _tokenize_value(value)
        entries.append((field_name, bio_tag, tokens))

    if doc_type == "aadhaar" and "address" in metadata:
        addr = metadata["address"]
        if isinstance(addr, dict):
            for addr_key in ["door", "street", "locality", "city", "state"]:
                val = addr.get(addr_key, "")
                if val:
                    entries.append((addr_key, "ADDRESS_LINE", _tokenize_value(val)))

    if doc_type == "bank_statement" and "transactions" in metadata:
        for i, txn in enumerate(metadata.get("transactions", [])):
            for txn_field, bio_tag in BANK_STATEMENT_TXN_LABELS.items():
                val = txn.get(txn_field)
                if val is not None and val != "":
                    entries.append(
                        (f"txn_{i}_{txn_field}", bio_tag, _tokenize_value(val))
                    )

    return entries


def annotate_document(
    image_path: Path,
    metadata: dict,
    ocr_engine: PaddleOCR | None = None,
) -> tuple[dict, dict]:
    """Annotate a single document image using OCR + metadata matching.

    Returns (layoutlmv3_annotation, donut_annotation).
    """
    if ocr_engine is None:
        ocr_engine = _init_ocr()

    img = Image.open(image_path)
    img_width, img_height = img.size

    result = ocr_engine.predict(str(image_path))

    doc_type = metadata.get("document_type", "unknown")
    gt_entries = _build_gt_lookup(metadata, doc_type)

    tokens: list[dict] = []
    if result:
        page = result[0]
        for text, confidence, bbox_raw in zip(
            page["rec_texts"], page["rec_scores"], page["rec_polys"], strict=True
        ):
            if confidence < 0.5:
                continue
            line_bbox = _normalize_bbox(bbox_raw, img_width, img_height)
            tokens.extend(_split_line_into_word_tokens(text, line_bbox, confidence))

    matched_fields: set[str] = set()

    for field_name, bio_tag, gt_tokens in gt_entries:
        gt_str = " ".join(gt_tokens).upper()
        exact = _is_exact_field(field_name) or _is_numeric_field(field_name)

        if len(gt_tokens) == 1:
            for tok in tokens:
                if tok["label"] != "O":
                    continue
                if _fuzzy_match(tok["text"], gt_tokens[0], exact=exact):
                    tok["label"] = f"B-{bio_tag}"
                    matched_fields.add(field_name)
                    break
        else:
            for start_idx in range(len(tokens)):
                if tokens[start_idx]["label"] != "O":
                    continue
                window = tokens[start_idx : start_idx + len(gt_tokens)]
                if len(window) < len(gt_tokens):
                    continue
                window_text = " ".join(t["text"] for t in window).upper()
                if _fuzzy_match(window_text, gt_str, exact=False):
                    window[0]["label"] = f"B-{bio_tag}"
                    for subsequent in window[1:]:
                        subsequent["label"] = f"I-{bio_tag}"
                    matched_fields.add(field_name)
                    break

    all_labels = get_bio_labels(doc_type)
    label2id = {l: i for i, l in enumerate(all_labels)}

    layoutlmv3_annotation = {
        "document_type": doc_type,
        "document_id": metadata.get("id", ""),
        "image_path": str(image_path),
        "image_size": {"width": img_width, "height": img_height},
        "tokens": [
            {
                "text": tok["text"],
                "bbox": tok["bbox"],
                "label": tok["label"],
                "label_id": label2id.get(tok["label"], 0),
            }
            for tok in tokens
        ],
        "label_schema": all_labels,
        "matched_fields": sorted(matched_fields),
        "total_gt_fields": len(gt_entries),
        "match_rate": len(matched_fields) / max(len(gt_entries), 1),
    }

    schema = LABEL_SCHEMAS.get(doc_type, {})
    gt_parse = {}
    for field_name in schema:
        val = metadata.get(field_name)
        if val is not None and val != "":
            gt_parse[field_name] = str(val)

    if doc_type == "aadhaar" and "address" in metadata:
        addr = metadata["address"]
        if isinstance(addr, dict):
            gt_parse["address"] = ", ".join(
                str(addr.get(k, ""))
                for k in ["door", "street", "locality", "city", "state", "pincode"]
                if addr.get(k)
            )

    donut_annotation = {
        "document_type": doc_type,
        "document_id": metadata.get("id", ""),
        "image_path": str(image_path),
        "gt_parse": gt_parse,
    }

    return layoutlmv3_annotation, donut_annotation


def annotate_directory(
    doc_dir: Path,
    output_dir: Path,
    ocr_engine: PaddleOCR | None = None,
) -> list[dict]:
    """Annotate all document images in a directory that have matching metadata JSON."""
    if ocr_engine is None:
        ocr_engine = _init_ocr()

    output_dir.mkdir(parents=True, exist_ok=True)
    results = []

    json_files = sorted(doc_dir.glob("*.json"))
    for json_path in json_files:
        with open(json_path) as f:
            metadata = json.load(f)

        doc_type = metadata.get("document_type", "unknown")
        doc_id = metadata.get("id", json_path.stem)

        image_patterns = [
            f"{doc_type}_{doc_id}.png",
            f"{doc_type}_{doc_id}.pdf",
            f"{doc_type}_front_{doc_id}.png",
            f"{doc_type}_{doc_id}_front.png",
        ]
        image_path = None
        for pattern in image_patterns:
            candidate = doc_dir / pattern
            if candidate.exists():
                image_path = candidate
                break

        if image_path is None:
            images = list(doc_dir.glob(f"*{doc_id}*.png")) + list(
                doc_dir.glob(f"*{doc_id}*.pdf")
            )
            if images:
                image_path = images[0]

        if image_path is None:
            logger.warning("No image found for %s (id=%s), skipping", json_path.name, doc_id)
            continue

        if image_path.suffix == ".pdf":
            try:
                from pdf2image import convert_from_path
                pages = convert_from_path(str(image_path), first_page=1, last_page=1)
                png_path = output_dir / f"{doc_type}_{doc_id}_page1.png"
                pages[0].save(png_path)
                image_path = png_path
            except ImportError:
                logger.warning("pdf2image required for PDF annotation, skipping %s", image_path.name)
                continue

        try:
            lmv3, donut = annotate_document(image_path, metadata, ocr_engine)
        except Exception:
            logger.exception("Failed to annotate %s", image_path.name)
            continue

        lmv3_path = output_dir / f"{doc_type}_{doc_id}_layoutlmv3.json"
        donut_path = output_dir / f"{doc_type}_{doc_id}_donut.json"
        with open(lmv3_path, "w") as f:
            json.dump(lmv3, f, indent=2)
        with open(donut_path, "w") as f:
            json.dump(donut, f, indent=2)

        results.append({
            "doc_id": doc_id,
            "doc_type": doc_type,
            "image": str(image_path),
            "match_rate": lmv3["match_rate"],
            "matched": len(lmv3["matched_fields"]),
            "total": lmv3["total_gt_fields"],
        })
        logger.info(
            "Annotated %s: %d/%d fields matched (%.0f%%)",
            doc_id, lmv3["matched_fields"].__len__(),
            lmv3["total_gt_fields"], lmv3["match_rate"] * 100,
        )

    return results


@click.command()
@click.option("--input-dir", "-i", type=click.Path(exists=True), required=True,
              help="Directory with generator output (images + JSON metadata)")
@click.option("--output-dir", "-o", type=click.Path(), required=True,
              help="Directory for annotation output")
@click.option("--doc-type", type=str, default=None,
              help="Filter by document type (pan, aadhaar, salary_slip, etc.)")
def main(input_dir: str, output_dir: str, doc_type: str | None) -> None:
    """Generate LayoutLMv3 and Donut annotations from generator output."""
    ocr = _init_ocr()
    in_path = Path(input_dir)
    out_path = Path(output_dir)

    results = annotate_directory(in_path, out_path, ocr)

    if doc_type:
        results = [r for r in results if r["doc_type"] == doc_type]

    total = len(results)
    if total == 0:
        click.echo("No documents annotated. Check input directory has images + JSON metadata.")
        return

    avg_match = sum(r["match_rate"] for r in results) / total
    click.echo(f"\nAnnotated {total} documents — average match rate: {avg_match:.1%}")

    for r in results:
        status = "✓" if r["match_rate"] >= 0.8 else "⚠"
        click.echo(f"  {status} {r['doc_type']}_{r['doc_id']}: {r['matched']}/{r['total']} fields")


if __name__ == "__main__":
    main()
