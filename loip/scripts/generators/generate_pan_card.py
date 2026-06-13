"""Generate synthetic PAN card images with ground-truth metadata."""

from __future__ import annotations

import random
import uuid
from pathlib import Path

import click
from PIL import Image, ImageDraw, ImageFont

from .base import fake, generate_pan, random_dob, save_metadata


def _render_pan_card(fields: dict, output_path: Path) -> Path:
    img = Image.new("RGB", (856, 540), color=(235, 235, 240))
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
        font_body = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
        font_pan = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
    except OSError:
        font_title = ImageFont.load_default()
        font_body = font_title
        font_pan = font_title

    draw.rectangle([(0, 0), (856, 70)], fill=(0, 51, 102))
    draw.text((200, 15), "INCOME TAX DEPARTMENT", fill="white", font=font_title)
    draw.text((250, 42), "GOVT. OF INDIA", fill="white", font=font_body)

    draw.rectangle([(30, 100), (170, 260)], outline=(150, 150, 150), width=2)
    draw.text((75, 170), "PHOTO", fill=(150, 150, 150), font=font_body)

    y = 100
    draw.text((200, y), "Permanent Account Number Card", fill=(0, 51, 102), font=font_body)
    y += 50
    draw.text((200, y), fields["pan_number"], fill=(0, 0, 0), font=font_pan)
    y += 50
    draw.text((200, y), f"Name: {fields['full_name']}", fill=(0, 0, 0), font=font_body)
    y += 35
    draw.text((200, y), f"Father's Name: {fields['father_name']}", fill=(0, 0, 0), font=font_body)
    y += 35
    draw.text((200, y), f"Date of Birth: {fields['date_of_birth']}", fill=(0, 0, 0), font=font_body)

    draw.rectangle([(630, 400), (810, 500)], outline=(150, 150, 150), width=1)
    draw.text((670, 440), "Signature", fill=(150, 150, 150), font=font_body)

    img_path = output_path / f"pan_{fields['id']}.png"
    img.save(img_path)
    return img_path


def generate_pan_card(
    output_dir: Path,
    tamper_type: str | None = None,
    name: str | None = None,
    father_name: str | None = None,
) -> dict:
    doc_id = uuid.uuid4().hex[:8]
    full_name = name or fake.name()
    f_name = father_name or fake.name_male()
    pan = generate_pan()
    dob = random_dob()

    fields = {
        "id": doc_id,
        "document_type": "pan",
        "pan_number": pan,
        "full_name": full_name.upper(),
        "father_name": f_name.upper(),
        "date_of_birth": dob.strftime("%d/%m/%Y"),
        "has_signature": True,
        "has_photo": True,
        "tamper_type": tamper_type,
    }

    if tamper_type == "pan_mismatch":
        chars = list(pan)
        idx = random.randint(5, 8)
        chars[idx] = str((int(chars[idx]) + random.randint(1, 5)) % 10) if chars[idx].isdigit() else random.choice("ABCDEFGH")
        fields["pan_number"] = "".join(chars)
    elif tamper_type == "identity_mismatch":
        name_parts = full_name.upper().split()
        if len(name_parts) > 1:
            name_parts[0], name_parts[-1] = name_parts[-1], name_parts[0]
        fields["full_name"] = " ".join(name_parts)
    elif tamper_type == "dob_mismatch":
        shifted = dob.replace(year=dob.year - random.randint(1, 3))
        fields["date_of_birth"] = shifted.strftime("%d/%m/%Y")
    elif tamper_type == "document_forgery":
        fields["_pdf_created_by"] = "Adobe Photoshop CC 2024"

    _render_pan_card(fields, output_dir)
    save_metadata(output_dir, "pan", fields)
    return fields


@click.command()
@click.option("--output", "-o", type=click.Path(), default="./output/pan_cards", help="Output directory")
@click.option("--count", "-n", type=int, default=1, help="Number to generate")
@click.option("--tamper-type", type=click.Choice(["pan_mismatch", "identity_mismatch", "dob_mismatch", "document_forgery"]), default=None)
def main(output: str, count: int, tamper_type: str | None) -> None:
    out = Path(output)
    for i in range(count):
        fields = generate_pan_card(out, tamper_type=tamper_type)
        click.echo(f"[{i+1}/{count}] Generated PAN: {fields['pan_number']} — {fields['full_name']}")


if __name__ == "__main__":
    main()
