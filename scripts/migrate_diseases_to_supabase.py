"""
Migration Script: disease_database.py -> Supabase diseases table

วิธีใช้:
1. รัน SQL script ก่อน: scripts/setup_diseases_table.sql
2. รัน: python scripts/migrate_diseases_to_supabase.py

หมายเหตุ:
- ต้องมี OPENAI_API_KEY และ SUPABASE_URL/KEY ใน .env
- Script นี้จะ upsert (update หรือ insert) ข้อมูลโรค
- ใช้เวลาประมาณ 2-5 นาที (ขึ้นอยู่กับจำนวนโรค)
"""

import asyncio
import json
import logging
import sys
import os
from typing import Dict, List, Any
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import AsyncOpenAI
from supabase import create_client

# Import existing database
from app.services.disease_database import (
    FUNGAL_DISEASES,
    BACTERIAL_DISEASES,
    VIRAL_DISEASES,
    INSECT_PESTS,
    NUTRIENT_DEFICIENCIES,
)

# Try to import WEEDS (may not exist)
try:
    from app.services.disease_database import WEEDS
except ImportError:
    WEEDS = {}
from app.config import OPENAI_API_KEY, SUPABASE_URL, SUPABASE_KEY

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize clients
openai_client = None
supabase = None

if OPENAI_API_KEY:
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    logger.info("OpenAI client initialized")

if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("Supabase client initialized")


async def generate_embedding(text: str) -> List[float]:
    """Generate embedding using OpenAI text-embedding-3-small"""
    if not openai_client:
        raise ValueError("OpenAI client not initialized")

    response = await openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
        encoding_format="float"
    )
    return response.data[0].embedding


def create_embedding_text(disease: Dict, category: str) -> str:
    """Create text for embedding from disease data"""
    parts = []

    # Name (highest weight)
    if disease.get('name_th'):
        parts.append(disease['name_th'])
    if disease.get('name_en'):
        parts.append(disease['name_en'])

    # Category in Thai
    category_map = {
        'fungal': 'โรคเชื้อรา',
        'bacterial': 'โรคแบคทีเรีย',
        'viral': 'โรคไวรัส',
        'insect': 'แมลงศัตรูพืช',
        'nutrient': 'อาการขาดธาตุอาหาร',
        'weed': 'วัชพืช'
    }
    parts.append(category_map.get(category, category))

    # Pathogen
    if disease.get('pathogen'):
        parts.append(disease['pathogen'])

    # Vector pest (for viral diseases)
    if disease.get('vector'):
        parts.append(disease['vector'])

    # Host plants
    if disease.get('host_plants'):
        parts.extend(disease['host_plants'])

    # Symptoms (top 5)
    symptoms = disease.get('symptoms', disease.get('appearance', []))
    if symptoms and isinstance(symptoms, list):
        parts.extend(symptoms[:5])

    # Key features (top 3)
    if disease.get('key_features'):
        parts.extend(disease['key_features'][:3])

    # Distinguish from
    if disease.get('distinguish_from'):
        parts.append(disease['distinguish_from'])

    # Damage (for insects)
    if disease.get('damage'):
        damage = disease['damage']
        if isinstance(damage, list):
            parts.extend(damage[:3])

    return ' '.join(filter(None, parts))


def prepare_disease_data(key: str, disease: Dict, category: str) -> Dict[str, Any]:
    """Prepare disease data for Supabase insert"""

    # Handle symptoms - could be list or dict
    symptoms = disease.get('symptoms', disease.get('appearance', []))
    if not isinstance(symptoms, list):
        symptoms = []

    # Handle key_features
    key_features = disease.get('key_features', [])
    if not isinstance(key_features, list):
        key_features = []

    # Handle severity_indicators
    severity_indicators = disease.get('severity_indicators', {})
    if not isinstance(severity_indicators, dict):
        severity_indicators = {}

    # Handle host_plants
    host_plants = disease.get('host_plants', [])
    if not isinstance(host_plants, list):
        host_plants = []

    # Handle affected_parts
    affected_parts = disease.get('affected_parts', disease.get('found_on', []))
    if not isinstance(affected_parts, list):
        affected_parts = []

    return {
        'disease_key': key,
        'name_th': disease.get('name_th', ''),
        'name_en': disease.get('name_en', ''),
        'category': category,
        'pathogen': disease.get('pathogen', disease.get('vector', '')),
        'vector_pest': disease.get('vector', ''),
        'host_plants': host_plants,
        'symptoms': symptoms,
        'key_features': key_features,
        'distinguish_from': disease.get('distinguish_from', ''),
        'affected_parts': affected_parts,
        'severity_indicators': severity_indicators,
        'treatment_methods': disease.get('treatment', []),
        'prevention_methods': disease.get('prevention', []),
        'is_active': True,
        'priority_score': 50
    }


async def migrate_category(diseases: Dict, category: str, stats: Dict):
    """Migrate all diseases in a category"""
    if not diseases:
        logger.info(f"No diseases in category: {category}")
        return

    logger.info(f"\n{'='*60}")
    logger.info(f"Migrating {category.upper()} diseases: {len(diseases)} items")
    logger.info(f"{'='*60}")

    for key, disease in diseases.items():
        try:
            # Create embedding text
            embed_text = create_embedding_text(disease, category)
            logger.debug(f"Embedding text for {key}: {embed_text[:100]}...")

            # Generate embedding
            embedding = await generate_embedding(embed_text)

            # Prepare data
            data = prepare_disease_data(key, disease, category)
            data['embedding'] = embedding

            # Upsert to Supabase
            result = supabase.table('diseases').upsert(
                data,
                on_conflict='disease_key'
            ).execute()

            logger.info(f"  ✓ {key}: {disease.get('name_th', '')} ({disease.get('name_en', '')})")
            stats['success'] += 1

            # Rate limiting - avoid hitting API limits
            await asyncio.sleep(0.3)

        except Exception as e:
            logger.error(f"  ✗ Failed to migrate {key}: {e}")
            stats['failed'] += 1
            stats['errors'].append({'key': key, 'error': str(e)})


async def verify_migration():
    """Verify migration by counting records"""
    if not supabase:
        return

    result = supabase.table('diseases').select('id, category', count='exact').execute()

    if result.count:
        logger.info(f"\n{'='*60}")
        logger.info(f"VERIFICATION: Total diseases in database: {result.count}")
        logger.info(f"{'='*60}")

        # Count by category
        categories = {}
        for row in result.data:
            cat = row['category']
            categories[cat] = categories.get(cat, 0) + 1

        for cat, count in sorted(categories.items()):
            logger.info(f"  {cat}: {count}")


async def main():
    """Main migration function"""
    print("\n" + "="*60)
    print("  Disease Database Migration")
    print("  disease_database.py -> Supabase diseases table")
    print("="*60 + "\n")

    # Check clients
    if not openai_client:
        logger.error("OpenAI client not initialized. Check OPENAI_API_KEY")
        return

    if not supabase:
        logger.error("Supabase client not initialized. Check SUPABASE_URL and SUPABASE_KEY")
        return

    # Statistics
    stats = {
        'success': 0,
        'failed': 0,
        'errors': [],
        'start_time': datetime.now()
    }

    # Migrate all categories
    try:
        # Try to import WEEDS
        try:
            from app.services.disease_database import WEEDS
        except ImportError:
            WEEDS = {}
            logger.warning("WEEDS not found in disease_database.py")

        await migrate_category(FUNGAL_DISEASES, 'fungal', stats)
        await migrate_category(BACTERIAL_DISEASES, 'bacterial', stats)
        await migrate_category(VIRAL_DISEASES, 'viral', stats)
        await migrate_category(INSECT_PESTS, 'insect', stats)
        await migrate_category(NUTRIENT_DEFICIENCIES, 'nutrient', stats)
        await migrate_category(WEEDS, 'weed', stats)

    except Exception as e:
        logger.error(f"Migration error: {e}")

    # Summary
    stats['end_time'] = datetime.now()
    duration = (stats['end_time'] - stats['start_time']).total_seconds()

    print("\n" + "="*60)
    print("  MIGRATION SUMMARY")
    print("="*60)
    print(f"  Success: {stats['success']}")
    print(f"  Failed:  {stats['failed']}")
    print(f"  Duration: {duration:.1f} seconds")

    if stats['errors']:
        print("\n  Errors:")
        for err in stats['errors'][:5]:
            print(f"    - {err['key']}: {err['error'][:50]}")

    print("="*60 + "\n")

    # Verify
    await verify_migration()


if __name__ == "__main__":
    asyncio.run(main())
