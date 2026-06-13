"""Shared utilities for all document generators."""

from __future__ import annotations

import json
import random
import string
import uuid
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

fake = Faker("en_IN")

INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
    "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
]

INDIAN_CITIES = {
    "Maharashtra": ["Mumbai", "Pune", "Nagpur"],
    "Karnataka": ["Bengaluru", "Mysuru", "Hubli"],
    "Tamil Nadu": ["Chennai", "Coimbatore", "Madurai"],
    "Telangana": ["Hyderabad", "Warangal", "Nizamabad"],
    "Delhi": ["New Delhi"],
    "Uttar Pradesh": ["Lucknow", "Noida", "Agra"],
    "Gujarat": ["Ahmedabad", "Surat", "Vadodara"],
    "West Bengal": ["Kolkata", "Howrah", "Durgapur"],
    "Rajasthan": ["Jaipur", "Jodhpur", "Udaipur"],
    "Kerala": ["Thiruvananthapuram", "Kochi", "Kozhikode"],
}

EMPLOYER_TIERS = {
    1: ["State Bank of India", "Indian Railways", "ONGC", "BHEL", "ISRO"],
    2: ["TCS", "Infosys", "Wipro", "Google India", "Microsoft India", "Amazon India"],
    3: ["Bajaj Finance", "HDFC Bank", "ICICI Bank", "Reliance Industries", "Mahindra & Mahindra"],
    4: ["Zenith Technologies", "Primus Solutions", "CoreStack India", "DataVault Systems"],
    5: ["NovaTech Startups", "QuickServe Pvt Ltd", "UrbanPay Solutions", "FreshBasket India"],
}

BANK_NAMES = [
    "State Bank of India", "HDFC Bank", "ICICI Bank", "Axis Bank",
    "Kotak Mahindra Bank", "Bank of Baroda", "Punjab National Bank",
    "Union Bank of India", "Canara Bank", "IndusInd Bank",
]


def generate_pan() -> str:
    first_five = "".join(random.choices(string.ascii_uppercase, k=5))
    middle_four = "".join(random.choices(string.digits, k=4))
    last = random.choice(string.ascii_uppercase)
    return f"{first_five}{middle_four}{last}"


def generate_aadhaar() -> str:
    digits = [random.randint(2, 9)] + [random.randint(0, 9) for _ in range(11)]
    return "".join(str(d) for d in digits)


def generate_uan() -> str:
    return "".join(random.choices(string.digits, k=12))


def random_dob(min_age: int = 22, max_age: int = 55) -> date:
    today = date.today()
    age = random.randint(min_age, max_age)
    return today - timedelta(days=age * 365 + random.randint(0, 364))


def random_indian_address() -> dict:
    state = random.choice(list(INDIAN_CITIES.keys()))
    city = random.choice(INDIAN_CITIES[state])
    return {
        "door": f"{random.randint(1, 500)}/{random.choice(string.ascii_uppercase)}",
        "street": fake.street_name(),
        "locality": fake.city_suffix() + " Nagar",
        "city": city,
        "state": state,
        "pincode": str(random.randint(100000, 999999)),
    }


def random_employer(tier: int | None = None) -> tuple[str, int]:
    if tier is None:
        tier = random.choices([1, 2, 3, 4, 5], weights=[10, 25, 30, 20, 15])[0]
    name = random.choice(EMPLOYER_TIERS[tier])
    return name, tier


def random_salary_components(tier: int) -> dict:
    base_ranges = {1: (25000, 80000), 2: (35000, 120000), 3: (30000, 100000), 4: (20000, 60000), 5: (18000, 45000)}
    low, high = base_ranges[tier]
    basic = random.randint(low, high)
    hra = int(basic * random.uniform(0.40, 0.50))
    conveyance = random.choice([1600, 3200, 5000])
    special_allowance = int(basic * random.uniform(0.10, 0.30))
    gross = basic + hra + conveyance + special_allowance
    pf = int(basic * 0.12)
    pt = random.choice([0, 200, 250])
    tds = int(gross * random.uniform(0.05, 0.20))
    net = gross - pf - pt - tds
    return {
        "basic": basic,
        "hra": hra,
        "conveyance": conveyance,
        "special_allowance": special_allowance,
        "gross_pay": gross,
        "pf_deduction": pf,
        "professional_tax": pt,
        "tds_deduction": tds,
        "net_pay": net,
    }


def save_metadata(output_dir: Path, doc_type: str, metadata: dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    meta_path = output_dir / f"{doc_type}_{metadata.get('id', uuid.uuid4().hex[:8])}.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    return meta_path
