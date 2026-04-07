"""MedHarmony A2A Agent Server.

FastAPI server implementing the A2A (Agent-to-Agent) protocol.
Endpoints:
  GET  /.well-known/agent.json  → Agent Card (discovery)
  POST /a2a                     → JSON-RPC for tasks/send, tasks/get
  GET  /health                  → Health check
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from src.agent.agent_card import get_agent_card
from src.agent.config import A2A_HOST, A2A_PORT, LOG_LEVEL
from src.agent.handler import TaskHandler


# =============================================================================
# Lifespan
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown."""
    logger.info("🏥 MedHarmony Agent starting up...")
    logger.info(f"   A2A endpoint: http://{A2A_HOST}:{A2A_PORT}/a2a")
    logger.info(f"   Agent Card:   http://{A2A_HOST}:{A2A_PORT}/.well-known/agent.json")
    yield
    logger.info("MedHarmony Agent shutting down.")


# =============================================================================
# App
# =============================================================================

app = FastAPI(
    title="MedHarmony A2A Agent",
    description="Intelligent Medication Reconciliation & Safety Agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

handler = TaskHandler()


# =============================================================================
# A2A Discovery Endpoint
# =============================================================================

@app.get("/.well-known/agent.json")
async def agent_card():
    """Return the A2A Agent Card for discovery.

    The Prompt Opinion platform and other A2A agents fetch this
    endpoint to learn about MedHarmony's capabilities.
    """
    return JSONResponse(content=get_agent_card())


# =============================================================================
# A2A JSON-RPC Endpoint
# =============================================================================

@app.post("/a2a")
async def a2a_endpoint(request: Request):
    """A2A JSON-RPC endpoint.

    Handles:
    - tasks/send: Submit a new task for processing
    - tasks/get: Retrieve the status/result of a task
    - tasks/cancel: Cancel a running task
    """
    try:
        body = await request.json()
    except Exception:
        return _jsonrpc_error(None, -32700, "Parse error")

    method = body.get("method")
    params = body.get("params", {})
    rpc_id = body.get("id", str(uuid.uuid4()))

    logger.info(f"A2A RPC call: method={method}, rpc_id={rpc_id}")

    if method == "tasks/send":
        return await _handle_tasks_send(rpc_id, params)
    elif method == "tasks/get":
        return await _handle_tasks_get(rpc_id, params)
    elif method == "tasks/cancel":
        return await _handle_tasks_cancel(rpc_id, params)
    else:
        return _jsonrpc_error(rpc_id, -32601, f"Method not found: {method}")


async def _handle_tasks_send(rpc_id: str, params: dict) -> JSONResponse:
    """Handle tasks/send: process a new task."""
    task_id = params.get("id", str(uuid.uuid4()))

    # Build task request
    task_request = {
        "id": task_id,
        "messages": params.get("messages", []),
        "metadata": params.get("metadata", {}),
    }

    # Process task (synchronous for now — could be async with SSE)
    result = await handler.handle_task(task_request)

    return JSONResponse(content={
        "jsonrpc": "2.0",
        "id": rpc_id,
        "result": result,
    })


async def _handle_tasks_get(rpc_id: str, params: dict) -> JSONResponse:
    """Handle tasks/get: retrieve task status."""
    task_id = params.get("id")
    if not task_id:
        return _jsonrpc_error(rpc_id, -32602, "Missing task id")

    task = await handler.get_task(task_id)
    if not task:
        return _jsonrpc_error(rpc_id, -32602, f"Task not found: {task_id}")

    return JSONResponse(content={
        "jsonrpc": "2.0",
        "id": rpc_id,
        "result": task,
    })


async def _handle_tasks_cancel(rpc_id: str, params: dict) -> JSONResponse:
    """Handle tasks/cancel."""
    task_id = params.get("id")
    return JSONResponse(content={
        "jsonrpc": "2.0",
        "id": rpc_id,
        "result": {"id": task_id, "status": "canceled"},
    })


def _jsonrpc_error(rpc_id: str | None, code: int, message: str) -> JSONResponse:
    """Return a JSON-RPC error response."""
    return JSONResponse(
        content={
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": code, "message": message},
        },
        status_code=200,  # JSON-RPC errors use 200
    )


# =============================================================================
# Health & Utility Endpoints
# =============================================================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "agent": "MedHarmony", "version": "1.0.0"}


@app.get("/")
async def root():
    """Root redirect to agent card."""
    return {
        "agent": "MedHarmony",
        "description": "Intelligent Medication Reconciliation & Safety Agent",
        "agent_card": "/.well-known/agent.json",
        "a2a_endpoint": "/a2a",
    }


# =============================================================================
# Convenience: Direct API (for testing without A2A protocol)
# =============================================================================

@app.post("/api/analyze")
async def direct_analyze(request: Request):
    """Direct analysis endpoint for testing.

    Accepts a simple JSON body:
    {
        "patient_id": "...",
        "fhir_server_url": "..." (optional),
        "fhir_access_token": "..." (optional)
    }
    """
    body = await request.json()

    from src.models.medication import SharpContext
    from src.core.reconciliation import ReconciliationEngine

    sharp_ctx = SharpContext(
        patient_id=body.get("patient_id", "demo-001"),
        fhir_server_url=body.get("fhir_server_url"),
        fhir_access_token=body.get("fhir_access_token"),
    )

    engine = ReconciliationEngine()
    result = await engine.run_full_analysis(sharp_ctx)

    return JSONResponse(content=result.model_dump())


# =============================================================================
# Main
# =============================================================================

def main():
    """Run the MedHarmony A2A server."""
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=""),
        level=LOG_LEVEL,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )

    uvicorn.run(
        "src.agent.server:app",
        host=A2A_HOST,
        port=A2A_PORT,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
