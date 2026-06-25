from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional
import jwt as pyjwt
import json, uuid, asyncpg, os, io
from datetime import datetime

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SSO_JWT_SECRET = os.getenv(
    "SSO_JWT_SECRET",
    "nexlayer-shared-sso-secret-change-in-production-64chars!!"
)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://gv_app:gv_secret_2026@postgres:5432/graphvault"
)

TIER_LIMITS = {
    "FREE":  {"max_graphs": 2,    "max_nodes": 10_000},
    "PRO":   {"max_graphs": 20,   "max_nodes": 500_000},
    "MAX":   {"max_graphs": None, "max_nodes": None},
    "ADMIN": {"max_graphs": None, "max_nodes": None},
}

# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------

app = FastAPI(title="GraphVault API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# DB pool
# ---------------------------------------------------------------------------

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL)
    return _pool


@app.on_event("startup")
async def startup():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS graphs (
                id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_email       VARCHAR(255) NOT NULL,
                project_name     VARCHAR(255) NOT NULL,
                description      TEXT DEFAULT '',
                node_count       INTEGER DEFAULT 0,
                edge_count       INTEGER DEFAULT 0,
                community_count  INTEGER DEFAULT 0,
                graph_data       JSONB NOT NULL DEFAULT '{}',
                html_content     TEXT,
                report_content   TEXT,
                created_at       TIMESTAMPTZ DEFAULT NOW(),
                updated_at       TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(user_email, project_name)
            );
            CREATE INDEX IF NOT EXISTS idx_graphs_user_email ON graphs(user_email);
        """)


@app.on_event("shutdown")
async def shutdown():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

async def get_current_user(authorization: str = Header(...)) -> dict:
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = pyjwt.decode(
            token,
            SSO_JWT_SECRET,
            algorithms=["HS256", "HS384"],
        )
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class GraphUpsert(BaseModel):
    project_name: str
    description: Optional[str] = ""
    graph_data: dict
    html_content: Optional[str] = None
    report_content: Optional[str] = None


class QueryRequest(BaseModel):
    question: str
    limit: Optional[int] = 20


class McpRequest(BaseModel):
    jsonrpc: Optional[str] = "2.0"
    id: Optional[str | int] = None
    method: str
    params: Optional[dict] = None


# ---------------------------------------------------------------------------
# Service helpers
# ---------------------------------------------------------------------------

def _do_query(nodes: list, edges: list, question: str, limit: int) -> dict:
    words = question.lower().split()

    matched_node_ids: set[str] = set()
    for node in nodes:
        node_id = str(node.get("id", ""))
        label = str(node.get("label", ""))
        combined = (node_id + " " + label).lower()
        if any(w in combined for w in words):
            matched_node_ids.add(node_id)

    matched_edges = []
    neighbor_ids: set[str] = set()
    for edge in edges:
        src = str(edge.get("source", edge.get("from", "")))
        tgt = str(edge.get("target", edge.get("to", "")))
        if src in matched_node_ids or tgt in matched_node_ids:
            matched_edges.append(edge)
            neighbor_ids.add(src)
            neighbor_ids.add(tgt)

    all_relevant_ids = matched_node_ids | neighbor_ids
    relevant_nodes = [
        n for n in nodes if str(n.get("id", "")) in all_relevant_ids
    ]

    return {
        "matched_nodes": len(matched_node_ids),
        "nodes": relevant_nodes[:limit],
        "edges": matched_edges[:limit * 3],
        "totals": {
            "nodes": len(relevant_nodes),
            "edges": len(matched_edges),
        },
    }


def _compute_counts(graph_data: dict) -> tuple[int, int, int]:
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    node_count = len(nodes)
    edge_count = len(edges)
    communities = {n.get("community") for n in nodes if n.get("community") is not None}
    community_count = len(communities)
    return node_count, edge_count, community_count


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "graphvault-api"}


@app.post("/v1/graphs")
async def upsert_graph(
    body: GraphUpsert,
    user: dict = Depends(get_current_user),
):
    pool = await get_pool()
    email = user.get("sub", "")
    tier = user.get("tier", "FREE")
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["FREE"])

    async with pool.acquire() as conn:
        # Tier check — graph count
        if limits["max_graphs"] is not None:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM graphs WHERE user_email = $1", email
            )
            existing = await conn.fetchval(
                "SELECT id FROM graphs WHERE user_email = $1 AND project_name = $2",
                email, body.project_name,
            )
            if existing is None and count >= limits["max_graphs"]:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Graph limit reached for {tier} tier "
                        f"({limits['max_graphs']} graphs). "
                        "Upgrade your plan to create more graphs."
                    ),
                )

        # Tier check — node count
        node_count, edge_count, community_count = _compute_counts(body.graph_data)
        if limits["max_nodes"] is not None and node_count > limits["max_nodes"]:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Node limit exceeded for {tier} tier "
                    f"(max {limits['max_nodes']:,} nodes). "
                    "Upgrade your plan to store larger graphs."
                ),
            )

        # UPSERT
        row = await conn.fetchrow(
            """
            INSERT INTO graphs
                (user_email, project_name, description, graph_data,
                 html_content, report_content,
                 node_count, edge_count, community_count, updated_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, NOW())
            ON CONFLICT (user_email, project_name)
            DO UPDATE SET
                description     = EXCLUDED.description,
                graph_data      = EXCLUDED.graph_data,
                html_content    = EXCLUDED.html_content,
                report_content  = EXCLUDED.report_content,
                node_count      = EXCLUDED.node_count,
                edge_count      = EXCLUDED.edge_count,
                community_count = EXCLUDED.community_count,
                updated_at      = NOW()
            RETURNING id, project_name, node_count, edge_count,
                      (xmax = 0) AS was_inserted
            """,
            email,
            body.project_name,
            body.description or "",
            json.dumps(body.graph_data),
            body.html_content,
            body.report_content,
            node_count,
            edge_count,
            community_count,
        )

    message = "Graph saved" if row["was_inserted"] else "Graph updated"
    return {
        "id": str(row["id"]),
        "project_name": row["project_name"],
        "node_count": row["node_count"],
        "edge_count": row["edge_count"],
        "message": message,
    }


@app.get("/v1/graphs")
async def list_graphs(user: dict = Depends(get_current_user)):
    pool = await get_pool()
    email = user.get("sub", "")
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, project_name, description,
                   node_count, edge_count, community_count,
                   (html_content IS NOT NULL) AS has_html,
                   created_at, updated_at
            FROM graphs
            WHERE user_email = $1
            ORDER BY updated_at DESC
            """,
            email,
        )
    return [
        {
            "id": str(r["id"]),
            "project_name": r["project_name"],
            "description": r["description"],
            "node_count": r["node_count"],
            "edge_count": r["edge_count"],
            "community_count": r["community_count"],
            "has_html": r["has_html"],
            "created_at": r["created_at"].isoformat(),
            "updated_at": r["updated_at"].isoformat(),
        }
        for r in rows
    ]


@app.get("/v1/graphs/{graph_id}")
async def get_graph(graph_id: str, user: dict = Depends(get_current_user)):
    pool = await get_pool()
    email = user.get("sub", "")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, project_name, description,
                   node_count, edge_count, community_count,
                   graph_data, report_content,
                   (html_content IS NOT NULL) AS has_html,
                   created_at, updated_at
            FROM graphs
            WHERE id = $1 AND user_email = $2
            """,
            uuid.UUID(graph_id),
            email,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Graph not found")
    return {
        "id": str(row["id"]),
        "project_name": row["project_name"],
        "description": row["description"],
        "node_count": row["node_count"],
        "edge_count": row["edge_count"],
        "community_count": row["community_count"],
        "has_html": row["has_html"],
        "graph_data": row["graph_data"],
        "report_content": row["report_content"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


@app.get("/v1/graphs/{graph_id}/html", response_class=HTMLResponse)
async def get_graph_html(graph_id: str, user: dict = Depends(get_current_user)):
    pool = await get_pool()
    email = user.get("sub", "")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT html_content FROM graphs WHERE id = $1 AND user_email = $2",
            uuid.UUID(graph_id),
            email,
        )
    if row is None or row["html_content"] is None:
        raise HTTPException(status_code=404, detail="HTML content not available for this graph")
    return HTMLResponse(content=row["html_content"])


@app.get("/v1/graphs/{graph_id}/download")
async def download_graph(graph_id: str, user: dict = Depends(get_current_user)):
    pool = await get_pool()
    email = user.get("sub", "")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT project_name, graph_data FROM graphs WHERE id = $1 AND user_email = $2",
            uuid.UUID(graph_id),
            email,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Graph not found")

    safe_name = row["project_name"].replace(" ", "_")
    filename = f"{safe_name}-graph.json"
    content = json.dumps(row["graph_data"], indent=2).encode("utf-8")

    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.delete("/v1/graphs/{graph_id}", status_code=204)
async def delete_graph(graph_id: str, user: dict = Depends(get_current_user)):
    pool = await get_pool()
    email = user.get("sub", "")
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM graphs WHERE id = $1 AND user_email = $2",
            uuid.UUID(graph_id),
            email,
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Graph not found")


@app.post("/v1/graphs/{graph_id}/query")
async def query_graph(
    graph_id: str,
    body: QueryRequest,
    user: dict = Depends(get_current_user),
):
    pool = await get_pool()
    email = user.get("sub", "")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT graph_data FROM graphs WHERE id = $1 AND user_email = $2",
            uuid.UUID(graph_id),
            email,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Graph not found")

    graph_data = row["graph_data"]
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    return _do_query(nodes, edges, body.question, body.limit or 20)


# ---------------------------------------------------------------------------
# MCP endpoint
# ---------------------------------------------------------------------------

@app.post("/v1/mcp")
async def mcp_endpoint(
    body: McpRequest,
    user: dict = Depends(get_current_user),
):
    email = user.get("sub", "")
    req_id = body.id
    method = body.method
    params = body.params or {}

    # tools/list
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "list_graphs",
                        "description": "List all knowledge graphs for the authenticated user.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                    {
                        "name": "query_graph",
                        "description": "Search nodes and edges in a graph by natural language question.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "project_name": {
                                    "type": "string",
                                    "description": "Name of the graph project to query.",
                                },
                                "question": {
                                    "type": "string",
                                    "description": "Natural language question to search within the graph.",
                                },
                            },
                            "required": ["project_name", "question"],
                        },
                    },
                    {
                        "name": "get_graph_stats",
                        "description": "Get metadata and statistics for a specific graph.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "project_name": {
                                    "type": "string",
                                    "description": "Name of the graph project.",
                                },
                            },
                            "required": ["project_name"],
                        },
                    },
                ]
            },
        }

    # tools/call
    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        pool = await get_pool()

        if tool_name == "list_graphs":
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, project_name, description,
                           node_count, edge_count, community_count,
                           created_at, updated_at
                    FROM graphs
                    WHERE user_email = $1
                    ORDER BY updated_at DESC
                    """,
                    email,
                )
            graphs = [
                {
                    "id": str(r["id"]),
                    "project_name": r["project_name"],
                    "description": r["description"],
                    "node_count": r["node_count"],
                    "edge_count": r["edge_count"],
                    "community_count": r["community_count"],
                    "created_at": r["created_at"].isoformat(),
                    "updated_at": r["updated_at"].isoformat(),
                }
                for r in rows
            ]
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"graphs": graphs, "count": len(graphs)},
            }

        if tool_name == "query_graph":
            project_name = arguments.get("project_name", "")
            question = arguments.get("question", "")
            limit = int(arguments.get("limit", 20))
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT graph_data FROM graphs WHERE user_email = $1 AND project_name = $2",
                    email,
                    project_name,
                )
            if row is None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": f"Graph '{project_name}' not found"},
                }
            graph_data = row["graph_data"]
            nodes = graph_data.get("nodes", [])
            edges = graph_data.get("edges", [])
            result = _do_query(nodes, edges, question, limit)
            return {"jsonrpc": "2.0", "id": req_id, "result": result}

        if tool_name == "get_graph_stats":
            project_name = arguments.get("project_name", "")
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT id, project_name, description,
                           node_count, edge_count, community_count,
                           (html_content IS NOT NULL) AS has_html,
                           (report_content IS NOT NULL) AS has_report,
                           created_at, updated_at
                    FROM graphs
                    WHERE user_email = $1 AND project_name = $2
                    """,
                    email,
                    project_name,
                )
            if row is None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": f"Graph '{project_name}' not found"},
                }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "id": str(row["id"]),
                    "project_name": row["project_name"],
                    "description": row["description"],
                    "node_count": row["node_count"],
                    "edge_count": row["edge_count"],
                    "community_count": row["community_count"],
                    "has_html": row["has_html"],
                    "has_report": row["has_report"],
                    "created_at": row["created_at"].isoformat(),
                    "updated_at": row["updated_at"].isoformat(),
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }
