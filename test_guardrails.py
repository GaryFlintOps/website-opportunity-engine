"""
test_guardrails.py

Run guardrail pipeline against 10 mock businesses.
Goal: 30–50% rejection rate validates filter calibration.

Run with:
    python test_guardrails.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.guardrails import validate_image, compress_review, validate_business, final_guardrail_check
from src.enhancer   import generate_support_images, clean_review_phrase, infer_services
from src.preview    import detect_image_brightness, enforce_image_consistency


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_photos(count: int, width: int = 1200) -> list[dict]:
    return [{"url": f"https://lh3.google.com/photo{i}", "width": width} for i in range(count)]

def _make_reviews(texts: list[str]) -> list[dict]:
    return [{"text": t, "author": "Test User", "rating": 5} for t in texts]


# ── 10 Test Businesses ────────────────────────────────────────────────────────

BUSINESSES = [
    # 1. Strong bike shop — should PASS
    {
        "name":    "Pedal Pro Cycles",
        "rating":  4.8,
        "photos":  _make_photos(7),
        "reviews": _make_reviews([
            "Very knowledgeable staff — helped me pick the perfect road bike.",
            "Quick turnaround on my service, was in and out in an hour.",
            "Friendly service every time I visit, wouldn't go anywhere else.",
            "Best selection of bikes in the area by far.",
            "Got a professional bike fit, completely transformed my riding.",
        ]),
    },
    # 2. No name — should FAIL
    {
        "name":    "",
        "rating":  4.5,
        "photos":  _make_photos(6),
        "reviews": _make_reviews(["Friendly service.", "Quick turnaround."]),
    },
    # 3. Low rating — should FAIL
    {
        "name":    "Rusty Spoke Cycles",
        "rating":  3.2,
        "photos":  _make_photos(6),
        "reviews": _make_reviews(["Knowledgeable staff.", "Great selection."]),
    },
    # 4. Too few images — should FAIL
    {
        "name":    "Two-Wheel Boutique",
        "rating":  4.6,
        "photos":  _make_photos(3),
        "reviews": _make_reviews([
            "Knowledgeable staff who really understand cycling.",
            "Quick turnaround on every repair I've needed.",
        ]),
    },
    # 5. No compressible reviews — should FAIL
    {
        "name":    "Velo House",
        "rating":  4.3,
        "photos":  _make_photos(6),
        "reviews": _make_reviews([
            "A fine establishment I suppose.",
            "It was okay nothing to write home about.",
            "Would maybe come back one day.",
        ]),
    },
    # 6. Only 1 compressible review — should FAIL
    {
        "name":    "Chain Reaction Bikes",
        "rating":  4.5,
        "photos":  _make_photos(5),
        "reviews": _make_reviews([
            "Knowledgeable staff.",
            "It was alright I guess.",
        ]),
    },
    # 7. Good café (non-bike) — should PASS
    {
        "name":    "Morning Grounds Coffee",
        "rating":  4.7,
        "photos":  _make_photos(8),
        "reviews": _make_reviews([
            "Extremely friendly service, they remembered my name on the second visit.",
            "Quick turnaround even during the morning rush — impressive.",
            "Knowledgeable baristas who really care about their craft.",
            "Great selection of single origin beans.",
        ]),
    },
    # 8. Logo/text-heavy images — filtered images drop below minimum → FAIL
    {
        "name":    "SignBoard Cycles",
        "rating":  4.4,
        "photos":  [
            {"url": "https://lh3.google.com/photo0", "width": 1200},
            {"url": "https://lh3.google.com/photo1", "width": 1200},
            {"url": "https://lh3.google.com/logo",   "width": 1200, "type": "logo"},
            {"url": "https://lh3.google.com/photo3", "width": 500},   # too narrow
            {"url": "https://lh3.google.com/photo4", "width": 1200, "tags": ["text-heavy"]},
            {"url": "https://lh3.google.com/photo5", "width": 1200, "tags": ["duplicate"]},
            {"url": "https://lh3.google.com/photo6", "width": 1200},
        ],
        "reviews": _make_reviews([
            "Friendly service and great staff.",
            "Quick turnaround — had my bike back the next day.",
        ]),
    },
    # 9. Borderline pass — exactly meets minimums → should PASS
    {
        "name":    "Gears & Grace",
        "rating":  4.1,
        "photos":  _make_photos(5),
        "reviews": _make_reviews([
            "Very knowledgeable staff, helped me pick the right components.",
            "Friendly service — everyone was kind and welcoming.",
        ]),
    },
    # 10. High quality salon — should PASS
    {
        "name":    "Scissors & Soul Salon",
        "rating":  4.9,
        "photos":  _make_photos(9),
        "reviews": _make_reviews([
            "Extremely knowledgeable stylists who always deliver excellent results.",
            "Friendly service — I actually look forward to my appointments.",
            "Quick turnaround even on busy Saturdays.",
            "Great selection of treatments available.",
            "Always leave feeling transformed and happy.",
        ]),
    },
]


# ── Run Tests ─────────────────────────────────────────────────────────────────

def run_test():
    print("\n" + "═" * 70)
    print("  GUARDRAIL TEST — 10 businesses")
    print("═" * 70)

    passed_list  = []
    failed_list  = []

    for i, biz in enumerate(BUSINESSES, 1):
        name   = biz.get("name") or "<no name>"
        photos = biz.get("photos") or []
        reviews = biz.get("reviews") or []

        # Image filtering
        if photos and isinstance(photos[0], dict):
            valid_imgs = [img for img in photos if validate_image(img)]
        else:
            valid_imgs = photos

        # Review compression
        compressed = [
            compress_review(r.get("text", "") if isinstance(r, dict) else str(r))
            for r in reviews
        ]
        accepted = [c for c in compressed if c]

        # Business validation
        result = validate_business(biz)

        status = "✅ PASSED" if result else "❌ FAILED"
        label  = name or "<no name>"

        print(f"\n  [{i:02d}] {label}")
        print(f"       Rating:  {biz.get('rating', '—')}")
        print(f"       Images:  {len(photos)} total → {len(valid_imgs)} valid")
        print(f"       Reviews: {len(reviews)} total → {len(accepted)} accepted")
        print(f"       Status:  {status}")

        if result:
            passed_list.append(name)
        else:
            failed_list.append(name)

    passed_count = len(passed_list)
    failed_count = len(failed_list)
    total        = len(BUSINESSES)
    reject_pct   = round(failed_count / total * 100)

    print("\n" + "─" * 70)
    print(f"  SUMMARY: {passed_count} passed / {failed_count} failed  ({reject_pct}% rejected)")
    print("─" * 70)

    if reject_pct < 30:
        print("  ⚠  FILTERS TOO WEAK  — less than 30% rejected")
    elif reject_pct > 60:
        print("  ⚠  FILTERS TOO STRICT — more than 60% rejected")
    else:
        print("  ✅ FILTER CALIBRATION OK — within 30–60% rejection range")

    print("\n  Passed businesses:")
    for n in passed_list:
        print(f"    • {n}")

    print("\n  Rejected businesses:")
    for n in failed_list:
        print(f"    • {n}")


# ── Supplementary Unit Tests ──────────────────────────────────────────────────

def run_unit_tests():
    print("\n" + "═" * 70)
    print("  UNIT TESTS")
    print("═" * 70)
    errors = []

    # validate_image
    assert validate_image({"width": 1200}) is True,                              "wide image should pass"
    assert validate_image({"width": 400})  is False,                             "narrow image should fail"
    assert validate_image({"width": 1200, "type": "logo"})  is False,            "logo should fail"
    assert validate_image({"width": 1200, "tags": ["text-heavy"]}) is False,     "text-heavy should fail"
    assert validate_image({"width": 1200, "tags": ["duplicate"]})  is False,     "duplicate should fail"
    assert validate_image({"width": 1200, "category": "cycling"})  is True,      "cycling category should pass"
    print("  ✅ validate_image: all checks passed")

    # compress_review
    assert compress_review("The staff are so knowledgeable about bikes") == "Knowledgeable staff"
    assert compress_review("Very quick turnaround on my repair") == "Quick turnaround"
    assert compress_review("Such friendly service throughout") == "Friendly service"
    assert compress_review("Great selection of components") == "Great selection"
    assert compress_review("I got a professional bike fit") == "Excellent bike fit"
    assert compress_review("It was okay") is None
    assert compress_review("") is None
    print("  ✅ compress_review: all checks passed")

    # clean_review_phrase
    from src.enhancer import clean_review_phrase
    assert clean_review_phrase("  great service  ") == "Great service"
    assert clean_review_phrase("quick  turnaround") == "Quick turnaround"
    assert clean_review_phrase("") == ""
    print("  ✅ clean_review_phrase: all checks passed")

    # infer_services
    from src.enhancer import infer_services
    assert "Bike Sales" in infer_services("bike shop")
    assert "Specialty Coffee" in infer_services("cafe")
    assert len(infer_services("unknown category x")) == 4
    print("  ✅ infer_services: all checks passed")

    # generate_support_images
    from src.enhancer import generate_support_images
    assert len(generate_support_images("cycling", real_image_count=1)) <= 2
    assert generate_support_images("cycling", real_image_count=5) == []
    print("  ✅ generate_support_images: all checks passed")

    # enforce_image_consistency
    from src.preview import enforce_image_consistency
    urls = [
        "https://example.com/image1.jpg",
        "https://example.com/image2.jpg",
        "https://example.com/image1.jpg",   # duplicate
        "https://example.com/image3.jpg",
        "https://example.com/image4.jpg",
        "https://example.com/image5.jpg",
        "https://example.com/image6.jpg",
        "https://example.com/image7.jpg",   # 7th — should be capped
    ]
    result = enforce_image_consistency(urls)
    assert len(result) <= 6,         f"should cap at 6, got {len(result)}"
    assert len(set(result)) == len(result), "should have no duplicates"
    print("  ✅ enforce_image_consistency: all checks passed")

    # final_guardrail_check
    valid_data = {"name": "Test Biz", "rating": 4.5, "city": "Cape Town",
                  "review_phrases": ["Great service"], "gallery_images": []}
    try:
        final_guardrail_check(valid_data)
        print("  ✅ final_guardrail_check: valid data passes")
    except ValueError as e:
        errors.append(f"final_guardrail_check raised unexpectedly: {e}")

    try:
        final_guardrail_check({"name": "Test", "rating": 4.5, "city": "CT",
                                "review_phrases": ["This is way too long a phrase that exceeds eight words total now"],
                                "gallery_images": []})
        errors.append("final_guardrail_check should have raised for long phrase")
    except ValueError:
        print("  ✅ final_guardrail_check: correctly rejects long review phrase")

    try:
        final_guardrail_check({"name": "", "rating": 4.5, "city": "CT",
                                "review_phrases": [], "gallery_images": []})
        errors.append("final_guardrail_check should have raised for missing name")
    except ValueError:
        print("  ✅ final_guardrail_check: correctly rejects missing name")

    if errors:
        print("\n  ❌ UNIT TEST FAILURES:")
        for e in errors:
            print(f"    • {e}")
        return False

    print("\n  ✅ All unit tests passed")
    return True


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ok = run_unit_tests()
    run_test()
    if not ok:
        sys.exit(1)
