"""
Agentic RAG Pipeline for ICP Ladda Chatbot

4-Agent Architecture:
1. QueryUnderstandingAgent - Semantic intent detection, entity extraction, query expansion
2. RetrievalAgent - Multi-query retrieval, re-ranking, relevance filtering
3. GroundingAgent - Citation extraction, hallucination detection, answer verification
4. ResponseGeneratorAgent - Answer synthesis, citation formatting, confidence scoring
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum


class IntentType(str, Enum):
    """Types of user intents"""
    PRODUCT_INQUIRY = "product_inquiry"       # ถามเกี่ยวกับสินค้าเฉพาะ
    PRODUCT_RECOMMENDATION = "product_recommendation"  # ขอแนะนำสินค้า
    DISEASE_TREATMENT = "disease_treatment"   # การรักษาโรคพืช
    PEST_CONTROL = "pest_control"             # การกำจัดแมลง/ศัตรูพืช
    WEED_CONTROL = "weed_control"             # การกำจัดวัชพืช
    NUTRIENT_SUPPLEMENT = "nutrient_supplement"  # การเสริมธาตุอาหาร/บำรุง
    USAGE_INSTRUCTION = "usage_instruction"   # วิธีใช้/อัตราผสม
    GENERAL_AGRICULTURE = "general_agriculture"  # คำถามเกษตรทั่วไป
    GREETING = "greeting"                     # ทักทาย
    UNKNOWN = "unknown"                       # ไม่ทราบ


@dataclass
class QueryAnalysis:
    """Output from QueryUnderstandingAgent"""
    original_query: str
    intent: IntentType
    confidence: float
    entities: Dict[str, Any] = field(default_factory=dict)
    # Extracted entities: product_name, plant_type, disease_name, pest_name, etc.
    expanded_queries: List[str] = field(default_factory=list)
    required_sources: List[str] = field(default_factory=list)
    # Sources: products, diseases

    def __post_init__(self):
        if not self.expanded_queries:
            self.expanded_queries = [self.original_query]
        if not self.required_sources:
            self.required_sources = ["products"]


@dataclass
class RetrievedDocument:
    """A single retrieved document with metadata"""
    id: str
    title: str
    content: str
    source: str  # products, diseases
    similarity_score: float
    rerank_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Metadata: product_name, chemical_name, usage_rate, target_pest, category, etc.


@dataclass
class RetrievalResult:
    """Output from RetrievalAgent"""
    documents: List[RetrievedDocument]
    total_retrieved: int
    total_after_rerank: int
    avg_similarity: float
    avg_rerank_score: float
    sources_used: List[str] = field(default_factory=list)


@dataclass
class Citation:
    """A citation linking answer to source document"""
    doc_id: str
    doc_title: str
    source: str
    quoted_text: str
    confidence: float


@dataclass
class GroundingResult:
    """Output from GroundingAgent"""
    is_grounded: bool
    confidence: float
    citations: List[Citation]
    ungrounded_claims: List[str]
    suggested_answer: str
    grounding_notes: str = ""
    relevant_products: List[str] = field(default_factory=list)


@dataclass
class AgenticRAGResponse:
    """Final response from the Agentic RAG pipeline"""
    answer: str
    confidence: float
    citations: List[Citation]
    intent: IntentType
    is_grounded: bool
    sources_used: List[str]
    # Debug info
    query_analysis: Optional[QueryAnalysis] = None
    retrieval_result: Optional[RetrievalResult] = None
    grounding_result: Optional[GroundingResult] = None
    processing_time_ms: float = 0.0


# Export all components
__all__ = [
    "IntentType",
    "QueryAnalysis",
    "RetrievedDocument",
    "RetrievalResult",
    "Citation",
    "GroundingResult",
    "AgenticRAGResponse",
]
