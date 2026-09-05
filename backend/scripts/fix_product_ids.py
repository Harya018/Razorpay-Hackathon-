"""One-off repair script — Phase 20.

Re-running seed_catalog.py against an already-migrated catalog triggered a
latent bug: the 3 renamed-in-place products (matched by their OLD
pre-Phase-17 name via `match_name`) could no longer be found by that old
name, since a prior run had already renamed them. seed() treated them as
missing, created 3 brand-new rows (fresh auto-increment IDs), and then
deleted the old rows — which still held IDs 1/2/3 — as "stale."

Every real order in this project's history (all 162 of them) has
product_id 1, 2, or 3, and redteam's price-tampering assumptions
(tampering.py's PRODUCT_ID_LISTED_PRICE_HUMAN/_AGENT, merchant_rules.py's
PRODUCT_RULES[1]) are hardcoded to product ID 1/2 specifically. This
script moves the 3 recreated rows back onto their original IDs so every
existing foreign key (orders.product_id) resolves again, with no other
data touched.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal  # noqa: E402

# name -> the original ID it must be restored to (see docstring above)
RESTORE_TO = {
    "Hand-Painted Ceramic Table Vase": 1,
    "Hand-Thrown Stoneware Mug": 2,
    "Handwoven Jute Storage Basket - Large": 3,
}


def main():
    db = SessionLocal()
    try:
        placeholders = ",".join(f":n{i}" for i in range(len(RESTORE_TO)))
        params = {f"n{i}": name for i, name in enumerate(RESTORE_TO.keys())}
        rows = db.execute(text(f"SELECT id, name FROM products WHERE name IN ({placeholders})"), params).fetchall()
        print("Before:", rows)

        for name, target_id in RESTORE_TO.items():
            current = db.execute(text("SELECT id FROM products WHERE name = :n"), {"n": name}).fetchone()
            if current is None:
                print(f"SKIP (not found): {name}")
                continue
            current_id = current[0]
            if current_id == target_id:
                print(f"OK already correct: {name} id={current_id}")
                continue
            db.execute(text("UPDATE products SET id = :new WHERE id = :old"), {"new": target_id, "old": current_id})
            print(f"Moved: {name} {current_id} -> {target_id}")

        db.commit()

        after = db.execute(text("SELECT id, name FROM products ORDER BY id")).fetchall()
        print("\nAfter:")
        for r in after:
            print(" ", r)

        orphaned = db.execute(text(
            "SELECT COUNT(*) FROM orders WHERE product_id NOT IN (SELECT id FROM products)"
        )).scalar()
        print(f"\nOrphaned orders remaining: {orphaned}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
