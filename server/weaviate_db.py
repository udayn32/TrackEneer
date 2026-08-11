"""Weaviate vector database connection and management."""

import os
from typing import Optional
import weaviate
from weaviate.classes.config import Configure, Property, DataType
from weaviate.classes.init import Auth

# Configuration
WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY", None)

_client: Optional[weaviate.WeaviateClient] = None


def get_weaviate_client() -> weaviate.WeaviateClient:
    """Get or create Weaviate client instance."""
    global _client
    if _client is None:
        try:
            if WEAVIATE_API_KEY:
                _client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=WEAVIATE_URL,
                    auth_credentials=Auth.api_key(WEAVIATE_API_KEY),
                )
            else:
                _client = weaviate.connect_to_local(
                    host=WEAVIATE_URL.replace("http://", "").replace("https://", "").split(":")[0],
                    port=int(WEAVIATE_URL.split(":")[-1]) if ":" in WEAVIATE_URL else 8080,
                )
            
            print(f"✓ Connected to Weaviate at {WEAVIATE_URL}")
            _initialize_schema(_client)
        except Exception as e:
            print(f"✗ Failed to connect to Weaviate: {e}")
            rai
            se
    return _client


def _initialize_schema(client: weaviate.WeaviateClient) -> None:
    """Initialize Weaviate schema with collections for notes and subjects."""
    
    # Create Note collection if it doesn't exist
    if not client.collections.exists("Note"):
        client.collections.create(
            name="Note",
            description="Study notes with vector embeddings for semantic search",
            vectorizer_config=Configure.Vectorizer.text2vec_transformers(
                pooling_strategy="masked_mean"
            ),
            properties=[
                Property(
                    name="noteId",
                    data_type=DataType.TEXT,
                    description="Unique identifier from Neo4j"
                ),
                Property(
                    name="subjectId",
                    data_type=DataType.TEXT,
                    description="Parent subject ID"
                ),
                Property(
                    name="title",
                    data_type=DataType.TEXT,
                    description="Note title"
                ),
                Property(
                    name="description",
                    data_type=DataType.TEXT,
                    description="Note description"
                ),
                Property(
                    name="content",
                    data_type=DataType.TEXT,
                    description="Extracted text content from the note file"
                ),
                Property(
                    name="filename",
                    data_type=DataType.TEXT,
                    description="Original filename"
                ),
                Property(
                    name="fileType",
                    data_type=DataType.TEXT,
                    description="File type (PDF, TXT, etc.)"
                ),
                Property(
                    name="ownerEmail",
                    data_type=DataType.TEXT,
                    description="Owner email address"
                ),
                Property(
                    name="uploadedAt",
                    data_type=DataType.TEXT,
                    description="Upload timestamp"
                ),
            ]
        )
        print("✓ Created Note collection in Weaviate")
    
    # Create Subject collection if it doesn't exist
    if not client.collections.exists("Subject"):
        client.collections.create(
            name="Subject",
            description="Study subjects with embeddings for semantic organization",
            vectorizer_config=Configure.Vectorizer.text2vec_transformers(
                pooling_strategy="masked_mean"
            ),
            properties=[
                Property(
                    name="subjectId",
                    data_type=DataType.TEXT,
                    description="Unique identifier from Neo4j"
                ),
                Property(
                    name="name",
                    data_type=DataType.TEXT,
                    description="Subject name"
                ),
                Property(
                    name="description",
                    data_type=DataType.TEXT,
                    description="Subject description"
                ),
                Property(
                    name="ownerEmail",
                    data_type=DataType.TEXT,
                    description="Owner email address"
                ),
                Property(
                    name="createdAt",
                    data_type=DataType.TEXT,
                    description="Creation timestamp"
                ),
            ]
        )
        print("✓ Created Subject collection in Weaviate")


def close_weaviate_client() -> None:
    """Close Weaviate client connection."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
        print("✓ Closed Weaviate connection")


def health_check() -> dict:
    """Check Weaviate connection health."""
    try:
        client = get_weaviate_client()
        if client.is_ready():
            return {
                "status": "healthy",
                "message": "Weaviate is connected and ready",
                "url": WEAVIATE_URL
            }
        else:
            return {
                "status": "unhealthy",
                "message": "Weaviate is not ready",
                "url": WEAVIATE_URL
            }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "url": WEAVIATE_URL
        }
