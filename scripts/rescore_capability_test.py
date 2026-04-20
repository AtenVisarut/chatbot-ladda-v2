"""
Re-score an existing jsonl cache with updated scorer logic (no API calls).

Usage:
  python scripts/rescore_capability_test.py <cache.jsonl>
  # produces <cache>.rescored.xlsx + prints summary
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

os.environ.setdefault("ADMIN_PASSWORD", "rescore-only")
os.environ.setdefault("SECRET_KEY", "rescore-only-secret-key-1234")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.dependencies import supabase_client

from tests.capability_scorer import (
    score_product_info, score_pest_crop, score_usage_rate,
    score_moa, score_selling_point, score_comparison,
)

from scripts.run_capability_test import (
    export_excel, ProductResult, CellResult, pick_compare_partner,
)


def fetch_all_products() -> dict:
    r = supabase_client.table("products3").select(
        "product_name, common_name_th, active_ingredient, product_category, "
        "applicable_crops, fungicides, insecticides, herbicides, biostimulant, "
        "pgr_hormones, fertilizer, how_to_use, usage_rate, usage_period, "
        "selling_point, absorption_method, mechanism_of_action, physical_form, "
        "chemical_group_rac, caution_notes, package_size"
    ).execute()
    return {p["product_name"]: p for p in (r.data or [])}


def rescore_cell(cell: dict, product: dict, partner: Optional[dict]) -> int:
    cap = cell["capability"]
    ans = cell.get("answer", "")
    if cap == 1:
        s = score_product_info(ans, product)
    elif cap == 2:
        s = score_pest_crop(ans, product)
    elif cap == 3:
        s = score_usage_rate(ans, product)
    elif cap == 4:
        s = score_moa(ans, product)
    elif cap == 5:
        s = score_selling_point(ans, product)
    elif cap == 6:
        if not partner:
            return cell.get("score", 0)
        s = score_comparison(ans, product, partner)
    else:
        return cell.get("score", 0)
    cell["score"] = s.score
    cell["reason"] = s.reason
    return s.score


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/rescore_capability_test.py <cache.jsonl>")
        sys.exit(1)
    cache_path = Path(sys.argv[1])
    if not cache_path.exists():
        print(f"Cache not found: {cache_path}")
        sys.exit(1)

    print(f"📥 Loading {cache_path}")
    all_products = fetch_all_products()
    all_product_list = list(all_products.values())
    print(f"📦 DB has {len(all_products)} products")

    # Load cache
    results = []
    with open(cache_path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            pr = ProductResult(product=d["product"], category=d["category"])
            for cdict in d["cells"]:
                cell = CellResult(
                    product=cdict["product"],
                    capability=cdict["capability"],
                    question=cdict["question"],
                    answer=cdict.get("answer", ""),
                    score=cdict["score"],
                    reason=cdict["reason"],
                    error=cdict.get("error"),
                    elapsed_ms=cdict.get("elapsed_ms", 0),
                )
                pr.cells.append(cell)
            results.append(pr)
    print(f"📝 Loaded {len(results)} product results")

    # Re-score
    changes = 0
    for pr in results:
        product = all_products.get(pr.product)
        if not product:
            continue
        partner = pick_compare_partner(product, all_product_list)
        for cell in pr.cells:
            old_score = cell.score
            # Rebuild scorer call via dict form
            cell_dict = {
                "capability": cell.capability,
                "answer": cell.answer,
                "score": cell.score,
            }
            new_score = rescore_cell(cell_dict, product, partner)
            cell.score = cell_dict["score"]
            cell.reason = cell_dict["reason"]
            if old_score != new_score:
                changes += 1

    print(f"🔄 Re-scored: {changes} cells changed")

    # Write new Excel
    new_xlsx = cache_path.with_suffix(".rescored.xlsx")
    export_excel(results, new_xlsx)
    print(f"📊 Saved: {new_xlsx}")

    # Summary
    all_scores = [c.score for pr in results for c in pr.cells]
    overall = sum(all_scores) / len(all_scores) if all_scores else 0
    print(f"\n🏆 Overall average: {overall:.1f} / 100")
    for cap_id in (1, 2, 3, 4, 5, 6):
        scores = [c.score for pr in results for c in pr.cells if c.capability == cap_id]
        if scores:
            mean = sum(scores) / len(scores)
            passed = sum(1 for s in scores if s >= 70)
            print(f"   Cap #{cap_id}: {mean:5.1f}  ({passed}/{len(scores)} ≥70)")


if __name__ == "__main__":
    main()
