"""Seed the sample internship postings (idempotent).   python -m app.seed"""

from app.db import SessionLocal
from app.services import internship_service

if __name__ == "__main__":
    with SessionLocal() as db:
        added = internship_service.seed_samples(db)
    print(f"Added {added} sample internship(s)." if added else "Sample internships already present.")
