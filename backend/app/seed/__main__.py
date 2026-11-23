"""Seed sample internships and index the Product Knowledge Document (both idempotent).   python -m app.seed"""

from app.db import SessionLocal
from app.rag import product_kb
from app.services import internship_service

if __name__ == "__main__":
    with SessionLocal() as db:
        added = internship_service.seed_samples(db)
        print(f"Added {added} sample internship(s)." if added else "Sample internships already present.")
        r = product_kb.ingest(db)
        print(f"Product docs: {r['sections']} sections, {r['updated']} (re)indexed, {r['removed']} removed.")
