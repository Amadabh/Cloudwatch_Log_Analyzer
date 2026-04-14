import uuid
from langchain_core.tools import tool
from qdrant_client import QdrantClient, models

from log_pipeline import (
    logs_client,
    get_log_groups,
    fetch_all_logs,
    assign_request_ids,
    group_by_request_id,
    merge_continuations,
    create_rag_documents,
)

QDRANT_URL  = "http://localhost:6333"
COLLECTION  = "cloudwatch-documents"
MODEL_NAME  = "BAAI/bge-small-en"

qdrant = QdrantClient(url=QDRANT_URL)


# ── Tool 1 ────────────────────────────────────────────────────────────────────

@tool
def tool_get_log_groups() -> list[str]:
    """
    Returns all available CloudWatch log group names.
    Call this when the user asks what log groups or Lambda functions exist.
    """
    return get_log_groups(logs_client)


# ── Tool 2 ────────────────────────────────────────────────────────────────────

@tool
def tool_ingest(log_group: str) -> str:
    """
    Fetches logs from CloudWatch for the given log group, parses them,
    and stores them in Qdrant for semantic search.
    Call this when:
    - The user asks to ingest or refresh logs for a specific log group.
    - search_qdrant returns no results (logs not yet ingested).

    Args:
        log_group: Full log group name e.g. /aws/lambda/CoverLetterGen
    """
    raw  = fetch_all_logs(logs_client, log_group)
    raw  = assign_request_ids(raw)
    grp  = group_by_request_id(raw)
    for k in grp:
        grp[k] = merge_continuations(grp[k])
    docs = create_rag_documents(grp)

    if not qdrant.collection_exists(COLLECTION):
        qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config=models.VectorParams(
                size=qdrant.get_embedding_size(MODEL_NAME),
                distance=models.Distance.COSINE,
            ),
        )

    payloads = [{"text": d["page_content"], **d["metadata"]} for d in docs]
    texts    = [d["page_content"] for d in docs]
    ids      = [str(uuid.uuid4()) for _ in docs]

    qdrant.upload_collection(
        collection_name=COLLECTION,
        vectors=[models.Document(text=t, model=MODEL_NAME) for t in texts],
        payload=payloads,
        ids=ids,
    )

    return f"Ingested {len(docs)} documents from {log_group} into Qdrant."


# ── Tool 3 ────────────────────────────────────────────────────────────────────

@tool
def tool_search_qdrant(query: str, log_group: str = "") -> str:
    """
    Semantically searches stored log documents in Qdrant.
    Call this first when the user asks about errors, failures, or any
    specific event in the logs.

    Args:
        query:     Natural language question e.g. 'why did the function fail?'
        log_group: Optional. Filter results to a specific log group
                   e.g. /aws/lambda/CoverLetterGen. Leave empty to search all.

    Returns empty string if no documents are found — in that case call
    tool_ingest first, then try again.
    """
    query_filter = None
    if log_group:
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="log_group",
                    match=models.MatchValue(value=log_group),
                )
            ]
        )

    try:
        result = qdrant.query_points(
            collection_name=COLLECTION,
            query=models.Document(
                text=query,
                model=MODEL_NAME,
            ),
            query_filter=query_filter,
            limit=5,
        )
    except Exception:
        return ""

    hits = result.points
    if not hits:
        return ""

    docs = []
    for hit in hits:
        payload = hit.payload or {}
        text = payload.get("text")
        if text:
            docs.append(text)

    return "\n\n---\n\n".join(docs)


# ── Tool 4 ────────────────────────────────────────────────────────────────────

@tool
def tool_fetch_live_logs(log_group: str) -> str:
    """
    Fetches the latest raw logs directly from CloudWatch without using Qdrant.
    Call this when the user explicitly asks for the latest/real-time logs,
    or when you need a quick look without full ingestion.

    Args:
        log_group: Full log group name e.g. /aws/lambda/CoverLetterGen
    """
    raw  = fetch_all_logs(logs_client, log_group)
    raw  = assign_request_ids(raw)
    grp  = group_by_request_id(raw)
    for k in grp:
        grp[k] = merge_continuations(grp[k])
    docs = create_rag_documents(grp)

    return "\n\n---\n\n".join(d["page_content"] for d in docs[:5])


# ── Exported list for the agent ───────────────────────────────────────────────

tools = [
    tool_get_log_groups,
    tool_ingest,
    tool_search_qdrant,
    tool_fetch_live_logs,
]