"""Weaviate service for vector operations on study notes."""

import os
from pathlib import Path
from typing import List, Optional, Dict, Any
import PyPDF2
from weaviate_db import get_weaviate_client


class WeaviateService:
    """Service for managing vector embeddings and semantic search."""
    
    def __init__(self):
        self.client = get_weaviate_client()
        self.note_collection = self.client.collections.get("Note")
        self.subject_collection = self.client.collections.get("Subject")
    
    def extract_text_from_file(self, file_path: Path, file_type: str) -> str:
        """Extract text content from various file types."""
        try:
            if file_type.upper() == "PDF":
                return self._extract_text_from_pdf(file_path)
            elif file_type.upper() in ["TXT", "MD", "HTML", "CSS", "JS", "JSON"]:
                return file_path.read_text(encoding="utf-8", errors="ignore")
            else:
                return ""
        except Exception as e:
            print(f"Error extracting text from {file_path}: {e}")
            return ""
    
    def _extract_text_from_pdf(self, file_path: Path) -> str:
        """Extract text from PDF files."""
        text = ""
        try:
            with open(file_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
        except Exception as e:
            print(f"Error reading PDF {file_path}: {e}")
        return text.strip()
    
    def index_note(
        self,
        note_id: str,
        subject_id: str,
        title: str,
        description: str,
        file_path: Path,
        file_type: str,
        filename: str,
        owner_email: str,
        uploaded_at: str,
    ) -> bool:
        """Index a note in Weaviate with vector embeddings."""
        try:
            # Extract text content
            content = self.extract_text_from_file(file_path, file_type)
            
            # Create combined text for better embeddings
            combined_text = f"{title}\n{description}\n{content}"
            
            # Add to Weaviate
            self.note_collection.data.insert(
                properties={
                    "noteId": note_id,
                    "subjectId": subject_id,
                    "title": title,
                    "description": description,
                    "content": content[:50000],  # Limit content size
                    "filename": filename,
                    "fileType": file_type,
                    "ownerEmail": owner_email,
                    "uploadedAt": uploaded_at,
                },
            )
            
            print(f"✓ Indexed note {note_id} in Weaviate")
            return True
        except Exception as e:
            print(f"✗ Failed to index note {note_id}: {e}")
            return False
    
    def index_subject(
        self,
        subject_id: str,
        name: str,
        description: str,
        owner_email: str,
        created_at: str,
    ) -> bool:
        """Index a subject in Weaviate."""
        try:
            self.subject_collection.data.insert(
                properties={
                    "subjectId": subject_id,
                    "name": name,
                    "description": description,
                    "ownerEmail": owner_email,
                    "createdAt": created_at,
                },
            )
            
            print(f"✓ Indexed subject {subject_id} in Weaviate")
            return True
        except Exception as e:
            print(f"✗ Failed to index subject {subject_id}: {e}")
            return False
    
    def semantic_search_notes(
        self,
        query: str,
        owner_email: str,
        limit: int = 10,
        subject_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Perform semantic search on notes."""
        try:
            # Build filter
            filters = self.note_collection.query.Filter.by_property("ownerEmail").equal(owner_email)
            if subject_id:
                filters = filters & self.note_collection.query.Filter.by_property("subjectId").equal(subject_id)
            
            # Perform search
            response = self.note_collection.query.near_text(
                query=query,
                limit=limit,
                return_metadata=["distance", "score"],
                filters=filters,
            )
            
            # Format results
            results = []
            for item in response.objects:
                results.append({
                    "noteId": item.properties.get("noteId"),
                    "subjectId": item.properties.get("subjectId"),
                    "title": item.properties.get("title"),
                    "description": item.properties.get("description"),
                    "filename": item.properties.get("filename"),
                    "fileType": item.properties.get("fileType"),
                    "relevanceScore": 1 - item.metadata.distance if item.metadata.distance else 0,
                    "uploadedAt": item.properties.get("uploadedAt"),
                })
            
            return results
        except Exception as e:
            print(f"✗ Semantic search failed: {e}")
            return []
    
    def semantic_search_subjects(
        self,
        query: str,
        owner_email: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Perform semantic search on subjects."""
        try:
            filters = self.subject_collection.query.Filter.by_property("ownerEmail").equal(owner_email)
            
            response = self.subject_collection.query.near_text(
                query=query,
                limit=limit,
                return_metadata=["distance"],
                filters=filters,
            )
            
            results = []
            for item in response.objects:
                results.append({
                    "subjectId": item.properties.get("subjectId"),
                    "name": item.properties.get("name"),
                    "description": item.properties.get("description"),
                    "relevanceScore": 1 - item.metadata.distance if item.metadata.distance else 0,
                    "createdAt": item.properties.get("createdAt"),
                })
            
            return results
        except Exception as e:
            print(f"✗ Semantic search failed: {e}")
            return []
    
    def delete_note(self, note_id: str) -> bool:
        """Delete a note from Weaviate."""
        try:
            filters = self.note_collection.query.Filter.by_property("noteId").equal(note_id)
            self.note_collection.data.delete_many(where=filters)
            print(f"✓ Deleted note {note_id} from Weaviate")
            return True
        except Exception as e:
            print(f"✗ Failed to delete note {note_id}: {e}")
            return False
    
    def delete_subject(self, subject_id: str) -> bool:
        """Delete a subject and all its notes from Weaviate."""
        try:
            # Delete all notes for this subject
            note_filters = self.note_collection.query.Filter.by_property("subjectId").equal(subject_id)
            self.note_collection.data.delete_many(where=note_filters)
            
            # Delete the subject
            subject_filters = self.subject_collection.query.Filter.by_property("subjectId").equal(subject_id)
            self.subject_collection.data.delete_many(where=subject_filters)
            
            print(f"✓ Deleted subject {subject_id} from Weaviate")
            return True
        except Exception as e:
            print(f"✗ Failed to delete subject {subject_id}: {e}")
            return False
    
    def get_similar_notes(
        self,
        note_id: str,
        owner_email: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Find similar notes based on vector similarity."""
        try:
            # First get the target note
            filters = self.note_collection.query.Filter.by_property("noteId").equal(note_id)
            target = self.note_collection.query.fetch_objects(
                filters=filters,
                limit=1,
            )
            
            if not target.objects:
                return []
            
            target_note = target.objects[0]
            
            # Search for similar notes
            owner_filter = self.note_collection.query.Filter.by_property("ownerEmail").equal(owner_email)
            response = self.note_collection.query.near_object(
                near_object=target_note.uuid,
                limit=limit + 1,  # +1 because it includes the source note
                return_metadata=["distance"],
                filters=owner_filter,
            )
            
            # Format and filter out the source note
            results = []
            for item in response.objects:
                if item.properties.get("noteId") != note_id:
                    results.append({
                        "noteId": item.properties.get("noteId"),
                        "subjectId": item.properties.get("subjectId"),
                        "title": item.properties.get("title"),
                        "description": item.properties.get("description"),
                        "filename": item.properties.get("filename"),
                        "similarity": 1 - item.metadata.distance if item.metadata.distance else 0,
                    })
            
            return results[:limit]
        except Exception as e:
            print(f"✗ Failed to find similar notes: {e}")
            return []


# Global instance
_weaviate_service: Optional[WeaviateService] = None


def get_weaviate_service() -> WeaviateService:
    """Get or create WeaviateService instance."""
    global _weaviate_service
    if _weaviate_service is None:
        _weaviate_service = WeaviateService()
    return _weaviate_service
