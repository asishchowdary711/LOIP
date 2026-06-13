"""Identity mismatch fixtures — PAN/Aadhaar/application name and DOB disagreements."""

EXTRACTED_FIELDS = {
    "pan_number": "ABCDE1234F",
    "full_name": "Rajesh Kumar",
    "date_of_birth": "01/01/1990",
    "aadhaar_number": "123456789012",
}

APPLICATION_DATA_NAME_MISMATCH = {
    "aadhaar_otp": "123456",
    "full_name": "Suresh Sharma",
    "date_of_birth": "01/01/1990",
}

APPLICATION_DATA_DOB_MISMATCH = {
    "aadhaar_otp": "123456",
    "full_name": "Rajesh Kumar",
    "date_of_birth": "15/06/1985",
}
