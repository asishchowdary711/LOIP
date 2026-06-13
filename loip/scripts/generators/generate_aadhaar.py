"""Generate synthetic Aadhaar card images (front + back) with ground-truth metadata."""

from __future__ import annotations

import random
import uuid
from pathlib import Path

import click
from PIL import Image, ImageDraw, ImageFont

from .base import fake, generate_aadhaar as _gen_aadhaar_number, random_dob, random_indian_address, save_metadata


def _render_aadhaar_front(fields: dict, output_path: Path) -> Path:
    img = Image.new("RGB", (856, 540), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
        font_body = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
        font_aadhaar = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 26)
    except OSError:
        font_title = ImageFont.load_default()
        font_body = font_title
        font_aadhaar = font_title

    draw.rectangle([(0, 0), (856, 60)], fill=(255, 153, 51))
    draw.text((250, 15), "GOVERNMENT OF INDIA", fill="white", font=font_title)

    draw.rectangle([(30, 80), (170, 240)], outline=(200, 200, 200), width=2)
    draw.text((75, 150), "PHOTO", fill=(180, 180, 180), font=font_body)

    y = 85
    draw.text((200, y), f"Name / नाम: {fields['full_name']}", fill="black", font=font_body)
    y += 35
    draw.text((200, y), f"DOB / जन्म तिथि: {fields['date_of_birth']}", fill="black", font=font_body)
    y += 35
    draw.text((200, y), f"Gender / लिंग: {fields['gender']}", fill="black", font=font_body)
    y += 50

    aadhaar = fields["aadhaar_number"]
    masked = f"XXXX XXXX {aadhaar[-4:]}"
    draw.text((200, y), masked, fill=(0, 0, 150), font=font_aadhaar)

    addr = fields["address"]
    y = 320
    draw.text((30, y), f"Address: {addr['door']}, {addr['street']}", fill="black", font=font_body)
    y += 25
    draw.text((30, y), f"{addr['locality']}, {addr['city']}", fill="black", font=font_body)
    y += 25
    draw.text((30, y), f"{addr['state']} — {addr['pincode']}", fill="black", font=font_body)

    draw.rectangle([(0, 510), (856, 540)], fill=(19, 136, 8))

    path = output_path / f"aadhaar_front_{fields['id']}.png"
    img.save(path)
    return path


def _render_aadhaar_back(fields: dict, output_path: Path) -> Path:
    img = Image.new("RGB", (856, 540), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        font_body = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
        font_aadhaar = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
    except OSError:
        font_body = ImageFont.load_default()
        font_aadhaar = font_body

    draw.rectangle([(0, 0), (856, 50)], fill=(255, 153, 51))
    draw.rectangle([(600, 100), (800, 300)], outline=(200, 200, 200), width=2)
    draw.text((660, 190), "QR CODE", fill=(180, 180, 180), font=font_body)

    aadhaar = fields["aadhaar_number"]
    formatted = f"{aadhaar[:4]} {aadhaar[4:8]} {aadhaar[8:]}"
    draw.text((50, 250), f"Aadhaar No: {formatted}", fill=(0, 0, 150), font=font_aadhaar)

    draw.rectangle([(0, 510), (856, 540)], fill=(19, 136, 8))

    path = output_path / f"aadhaar_back_{fields['id']}.png"
    img.save(path)
    return path


def generate_aadhaar(
    output_dir: Path,
    tamper_type: str | None = None,
    name: str | None = None,
) -> dict:
    doc_id = uuid.uuid4().hex[:8]
    full_name = name or fake.name()
    aadhaar_num = _gen_aadhaar_number()
    dob = random_dob()
    gender = random.choice(["Male", "Female"])
    address = random_indian_address()

    fields = {
        "id": doc_id,
        "document_type": "aadhaar",
        "aadhaar_number": aadhaar_num,
        "full_name": full_name,
        "date_of_birth": dob.strftime("%d/%m/%Y"),
        "gender": gender,
        "address": address,
        "pincode": address["pincode"],
        "tamper_type": tamper_type,
    }

    if tamper_type == "identity_mismatch":
        parts = full_name.split()
        if len(parts) > 1:
            fields["full_name"] = parts[-1] + " " + " ".join(parts[:-1])
    elif tamper_type == "dob_mismatch":
        shifted = dob.replace(year=dob.year + random.randint(1, 3))
        fields["date_of_birth"] = shifted.strftime("%d/%m/%Y")
    elif tamper_type == "synthetic_identity":
        fields["address"]["state"] = random.choice([s for s in ["Tamil Nadu", "Kerala", "Bihar", "Rajasthan"] if s != address["state"]])
    elif tamper_type == "document_forgery":
        fields["_pdf_created_by"] = "GIMP 2.10"

    output_dir.mkdir(parents=True, exist_ok=True)
    _render_aadhaar_front(fields, output_dir)
    _render_aadhaar_back(fields, output_dir)
    save_metadata(output_dir, "aadhaar", fields)
    return fields


@click.command()
@click.option("--output", "-o", type=click.Path(), default="./output/aadhaar_cards")
@click.option("--count", "-n", type=int, default=1)
@click.option("--tamper-type", type=click.Choice(["identity_mismatch", "dob_mismatch", "synthetic_identity", "document_forgery"]), default=None)
def main(output: str, count: int, tamper_type: str | None) -> None:
    out = Path(output)
    for i in range(count):
        fields = generate_aadhaar(out, tamper_type=tamper_type)
        click.echo(f"[{i+1}/{count}] Generated Aadhaar: ****{fields['aadhaar_number'][-4:]} — {fields['full_name']}")


if __name__ == "__main__":
    main()
