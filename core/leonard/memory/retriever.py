"""
Retriever for RAG-based content retrieval.
Fetches relevant context from the vault to augment LLM responses.
"""

from dataclasses import dataclass
from typing import Optional

from leonard.memory.vault import Vault, SearchResult
from leonard.utils.logging import logger


@dataclass
class RetrievalResult:
    """A single retrieval result with context."""

    content: str
    source: str
    score: float
    chunk_index: int


class Retriever:
    """
    RAG retriever with relevance scoring and context building.

    Fetches relevant document chunks from the vault based on
    semantic similarity to the query.
    """

    DEFAULT_TOP_K = 5
    MIN_RELEVANCE_SCORE = 0.3  # Minimum similarity score to include

    def __init__(self, vault: Vault):
        """
        Initialize the retriever.

        Args:
            vault: Vault instance for searching
        """
        self.vault = vault
        logger.info("Retriever initialized")

    async def retrieve(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = MIN_RELEVANCE_SCORE,
    ) -> list[RetrievalResult]:
        """
        Retrieve relevant chunks for a query.

        Args:
            query: Search query
            top_k: Maximum number of results
            min_score: Minimum relevance score (0-1)

        Returns:
            List of RetrievalResult objects sorted by relevance
        """
        if not query.strip():
            return []

        try:
            # Search the vault
            search_results = await self.vault.search(query, limit=top_k)

            # Filter by minimum score and convert to RetrievalResult
            results = []
            for sr in search_results:
                if sr.score >= min_score:
                    results.append(
                        RetrievalResult(
                            content=sr.content,
                            source=sr.source,
                            score=sr.score,
                            chunk_index=sr.metadata.get("chunk_index", 0),
                        )
                    )

            logger.info(f"Retrieved {len(results)} relevant chunks for query")
            return results

        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            return []

    async def retrieve_with_scores(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
    ) -> list[tuple[str, float]]:
        """
        Retrieve relevant context with relevance scores.

        Args:
            query: Search query
            top_k: Maximum number of results

        Returns:
            List of (content, score) tuples
        """
        results = await self.retrieve(query, top_k=top_k, min_score=0.0)
        return [(r.content, r.score) for r in results]

    def build_context(
        self,
        results: list[RetrievalResult],
        max_chars: int = 4000,
        include_sources: bool = True,
    ) -> str:
        """
        Build a context string from retrieval results.

        Args:
            results: List of RetrievalResult objects
            max_chars: Maximum total characters for context
            include_sources: Whether to include source citations

        Returns:
            Formatted context string
        """
        if not results:
            return ""

        context_parts = []
        total_chars = 0

        for i, result in enumerate(results):
            # Check if we have room for more content
            if total_chars >= max_chars:
                break

            # Format the chunk
            if include_sources:
                source_name = self._get_source_name(result.source)
                chunk_text = f"[{source_name}]\n{result.content}"
            else:
                chunk_text = result.content

            # Truncate if needed
            remaining_chars = max_chars - total_chars
            if len(chunk_text) > remaining_chars:
                chunk_text = chunk_text[:remaining_chars] + "..."

            context_parts.append(chunk_text)
            total_chars += len(chunk_text)

        return "\n\n---\n\n".join(context_parts)

    def format_for_prompt(
        self,
        results: list[RetrievalResult],
        max_chars: int = 4000,
    ) -> str:
        """
        Format results for injection into a prompt.

        Includes source citations and relevance indicators.

        Args:
            results: List of RetrievalResult objects
            max_chars: Maximum total characters

        Returns:
            Formatted string ready for prompt injection
        """
        if not results:
            return ""

        # Build header
        header = "The following information from your indexed documents may be relevant:\n"

        # Build content
        content_parts = []
        total_chars = len(header)

        for result in results:
            if total_chars >= max_chars:
                break

            source_name = self._get_source_name(result.source)
            relevance = "high" if result.score > 0.7 else "medium" if result.score > 0.5 else "low"

            chunk_text = f"**Source:** {source_name} (relevance: {relevance})\n{result.content}"

            # Truncate if needed
            remaining = max_chars - total_chars
            if len(chunk_text) > remaining:
                chunk_text = chunk_text[:remaining] + "..."

            content_parts.append(chunk_text)
            total_chars += len(chunk_text) + 10  # Account for separator

        if not content_parts:
            return ""

        return header + "\n\n".join(content_parts)

    def _get_source_name(self, source_path: str) -> str:
        """
        Extract a readable name from a source path.

        Args:
            source_path: Full path to the source

        Returns:
            Short, readable name
        """
        # Get just the filename
        if "/" in source_path:
            name = source_path.rsplit("/", 1)[-1]
        elif "\\" in source_path:
            name = source_path.rsplit("\\", 1)[-1]
        else:
            name = source_path

        # Truncate if too long
        if len(name) > 50:
            name = name[:47] + "..."

        return name

    async def get_context_for_query(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = MIN_RELEVANCE_SCORE,
        max_chars: int = 4000,
    ) -> Optional[str]:
        """
        Main entry point for RAG - get formatted context for a query.

        This is the method the orchestrator should call.

        Args:
            query: User's query/message
            top_k: Maximum chunks to retrieve
            min_score: Minimum relevance score
            max_chars: Maximum context length

        Returns:
            Formatted context string or None if no relevant content found
        """
        results = await self.retrieve(query, top_k=top_k, min_score=min_score)

        if not results:
            logger.debug(f"No relevant context found for query: {query[:50]}...")
            return None

        context = self.format_for_prompt(results, max_chars=max_chars)

        if context:
            logger.info(
                f"Built RAG context: {len(results)} chunks, "
                f"{len(context)} chars, "
                f"avg score: {sum(r.score for r in results) / len(results):.2f}"
            )

        return context if context else None
