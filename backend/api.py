from fastapi import FastAPI, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from agent import agent
import json
import uuid

app = FastAPI(title="CloudWatch Log Agent API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"

@app.get("/")
def health():
    return {"status": "ok"}

@app.get("/session/new")
def new_session():
    return {"thread_id": str(uuid.uuid4())}


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    async def generate():
        try:
            for event in agent.stream(
                {"messages": [{"role": "user", "content": req.message}]},
                config={"configurable": {"thread_id": req.thread_id}},
                stream_mode="values",
            ):
                last_msg = event["messages"][-1]
                msg_type = last_msg.__class__.__name__

                if msg_type == "AIMessage" and last_msg.tool_calls:
                    for tc in last_msg.tool_calls:
                        yield f"data: {json.dumps({'type': 'tool_call', 'name': tc['name']})}\n\n"
                elif msg_type == "ToolMessage":
                    yield f"data: {json.dumps({'type': 'tool_result', 'content': '✓ Tool completed'})}\n\n"
                elif msg_type == "AIMessage" and not last_msg.tool_calls:
                    yield f"data: {json.dumps({'type': 'token', 'content': last_msg.content})}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return EventSourceResponse(generate())