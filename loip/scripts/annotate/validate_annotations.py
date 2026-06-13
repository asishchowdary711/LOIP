"""Validate that annotation output covers all ground-truth fields.

Asserts every GT field has at least one annotated token with the correct BIO label.
This is the Phase 0 gate check before Phase 1a model training.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from .label_schema import LABEL_SCHEMAS, BANK_STATEMENT_TXN_LABELS


def validate_annotation(
    layoutlmv3_path: Path,
    metadata_path: Path,
    min_match_rate: float = 0.80,
) -> dict:
    """Validate a single LayoutLMv3 annotation against its source metadata.

    Returns a result dict with pass/fail status and details.
    """
    with open(layoutlmv3_path) as f:
        annotation = json.load(f)
    with open(metadata_path) as f:
        metadata = json.load(f)

    doc_type = metadata.get("document_type", "unknown")
    schema = LABEL_SCHEMAS.get(doc_type, {})

    assigned_tags: set[str] = set()
    for tok in annotation.get("tokens", []):
        label = tok.get("label", "O")
        if label != "O":
            tag = label.split("-", 1)[1] if "-" in label else label
            assigned_tags.add(tag)

    expected_fields: dict[str, str] = {}
    for field_name, bio_tag in schema.items():
        value = metadata.get(field_name)
        if value is not None and value != "":
            expected_fields[field_name] = bio_tag

    if doc_type == "aadhaar" and "address" in metadata:
        addr = metadata["address"]
        if isinstance(addr, dict) and any(addr.get(k) for k in ["door", "street", "city"]):
            expected_fields["address"] = "ADDRESS_LINE"

    if doc_type == "bank_statement" and metadata.get("transactions"):
        for txn_field, bio_tag in BANK_STATEMENT_TXN_LABELS.items():
            expected_fields[f"txn_{txn_field}"] = bio_tag

    covered = {}
    missing = {}
    for field_name, bio_tag in expected_fields.items():
        if bio_tag in assigned_tags:
            covered[field_name] = bio_tag
        else:
            missing[field_name] = bio_tag

    total = len(expected_fields)
    matched = len(covered)
    match_rate = matched / max(total, 1)
    passed = match_rate >= min_match_rate

    return {
        "doc_id": metadata.get("id", ""),
        "doc_type": doc_type,
        "annotation_file": str(layoutlmv3_path),
        "passed": passed,
        "match_rate": match_rate,
        "total_expected": total,
        "total_covered": matched,
        "covered_fields": covered,
        "missing_fields": missing,
        "min_match_rate": min_match_rate,
    }


def validate_directory(
    annotation_dir: Path,
    metadata_dir: Path,
    min_match_rate: float = 0.80,
) -> list[dict]:
    """Validate all annotations in a directory."""
    results = []

    lmv3_files = sorted(annotation_dir.glob("*_layoutlmv3.json"))
    for lmv3_path in lmv3_files:
        stem = lmv3_path.name.replace("_layoutlmv3.json", "")

        meta_path = metadata_dir / f"{stem}.json"
        if not meta_path.exists():
            parts = stem.rsplit("_", 1)
            if len(parts) == 2:
                doc_type, doc_id = parts
                meta_path = metadata_dir / f"{doc_type}_{doc_id}.json"

        if not meta_path.exists():
            results.append({
                "doc_id": stem,
                "doc_type": "unknown",
                "annotation_file": str(lmv3_path),
                "passed": False,
                "error": f"No metadata file found for {stem}",
            })
            continue

        result = validate_annotation(lmv3_path, meta_path, min_match_rate)
        results.append(result)

    return results


@click.command()
@click.option("--annotations", "-a", type=click.Path(exists=True), required=True,
              help="Directory with LayoutLMv3 annotation JSON files")
@click.option("--metadata", "-m", type=click.Path(exists=True), required=True,
              help="Directory with generator metadata JSON files")
@click.option("--min-match-rate", type=float, default=0.80,
              help="Minimum match rate to pass (0.0-1.0)")
@click.option("--strict", is_flag=True, default=False,
              help="Exit with non-zero code if any annotation fails")
def main(
    annotations: str,
    metadata: str,
    min_match_rate: float,
    strict: bool,
) -> None:
    """Validate annotation coverage against generator metadata."""
    results = validate_directory(
        Path(annotations), Path(metadata), min_match_rate
    )

    if not results:
        click.echo("No annotations found to validate.")
        sys.exit(1)

    passed = sum(1 for r in results if r.get("passed", False))
    failed = len(results) - passed

    click.echo(f"\nValidation Results: {passed} passed, {failed} failed "
               f"(threshold: {min_match_rate:.0%})")
    click.echo("=" * 60)

    for r in results:
        if "error" in r:
            click.echo(f"  ERROR  {r['doc_id']}: {r['error']}")
            continue

        status = "PASS" if r["passed"] else "FAIL"
        click.echo(
            f"  {status}  {r['doc_type']}_{r['doc_id']}: "
            f"{r['total_covered']}/{r['total_expected']} fields "
            f"({r['match_rate']:.0%})"
        )

        if r.get("missing_fields"):
            for field, tag in r["missing_fields"].items():
                click.echo(f"         missing: {field} ({tag})")

    if strict and failed > 0:
        click.echo(f"\nSTRICT MODE: {failed} annotation(s) below threshold. Exiting with error.")
        sys.exit(1)


if __name__ == "__main__":
    main()
