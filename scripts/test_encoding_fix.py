"""
Test Encoding Fix
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import clean_knowledge_text

def test_encoding_fix():
    print("=" * 60)
    print("Test Encoding Fix")
    print("=" * 60)
    
    # Test cases with corrupted text
    test_cases = [
        {
            "name": "จĞำ → จำ",
            "input": "เพลี้ยไฟเป็นแมลงจĞำพวกปากดูด",
            "expected": "เพลี้ยไฟเป็นแมลงจำพวกปากดูด"
        },
        {
            "name": "ลĞำ → ลำ",
            "input": "ลĞำตัวยาว มีทั้งชนิดมีปีก",
            "expected": "ลำตัวยาว มีทั้งชนิดมีปีก"
        },
        {
            "name": "ทĞำ → ทำ",
            "input": "เพื่อทĞำลายแหล่งอาศัย",
            "expected": "เพื่อทำลายแหล่งอาศัย"
        },
        {
            "name": "นĞ้ำ → น้ำ",
            "input": "สีนĞ้ำตาล และสีเหลือง",
            "expected": "สีน้ำตาล และสีเหลือง"
        },
        {
            "name": "กĞำ → กำ",
            "input": "ใช้สารกĞำจัดแมลง",
            "expected": "ใช้สารกำจัดแมลง"
        },
        {
            "name": "Real example",
            "input": "เพลี้ยไฟเป็นแมลงจĞำพวกปากดูดขนาดเล็ก ลĞำตัวยาว มีทั้งชนิดมีปีกและไม่มีปีก ตัวเต็มวัยมีสีดĞำ",
            "expected": "เพลี้ยไฟเป็นแมลงจำพวกปากดูดขนาดเล็ก ลำตัวยาว มีทั้งชนิดมีปีกและไม่มีปีก ตัวเต็มวัยมีสีดำ"
        }
    ]
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test['name']}")
        print(f"Input:    '{test['input']}'")
        
        result = clean_knowledge_text(test['input'])
        print(f"Output:   '{result}'")
        print(f"Expected: '{test['expected']}'")
        
        if result == test['expected']:
            print("✓ PASS")
            passed += 1
        else:
            print("✗ FAIL")
            failed += 1
    
    # Test with real corrupted text
    print("\n" + "=" * 60)
    print("Test with Real Corrupted Text")
    print("=" * 60)
    
    real_text = """เพลี้ยไฟ เพลี้ยไฟ ลักษณะอาการ ชื่อวิทยาศาสตร Stenchaetothrips biformis (Bagnall) รูปร่างลักษณะ เพลี้ยไฟเป็นแมลงจĞำพวกปากดูดขนาดเล็ก ลĞำตัวยาว มีทั้งชนิดมีปีกและไม่มีปีก ตัวเต็มวัยมีสีดĞำ ตัวอ่อนมีสีเหลืองอ่อน ตัวเต็มวัยเพศเมียวางไข่เดี่ยวๆ สีครีมในเนื้อเยื่อของใบข้าว"""
    
    print(f"\nOriginal:")
    print(real_text)
    
    cleaned = clean_knowledge_text(real_text)
    print(f"\nCleaned:")
    print(cleaned)
    
    # Check if Ğ is removed
    if 'Ğ' in cleaned:
        print("\n❌ Still has Ğ character")
    else:
        print("\n✓ All Ğ characters removed")
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

if __name__ == "__main__":
    test_encoding_fix()
