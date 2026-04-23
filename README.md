# ☁️ CloudWatch Log Analyzer

An AI-powered tool for analyzing AWS CloudWatch logs using natural language. Ask questions about your Lambda logs in plain English and get intelligent, context-aware answers — powered by **AWS Bedrock**, **LangGraph agents**, and **Qdrant** vector search.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=next.js&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-Bedrock%20%7C%20CloudWatch-FF9900?logo=amazon-aws&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Agent-1C3C3C?logo=langchain&logoColor=white)

---

## ✨ Features

- **Natural Language Queries** — Ask questions like _"What errors occurred in CoverLetterGen?"_ and get structured, human-readable answers.
- **Agentic Workflow** — A LangGraph ReAct agent autonomously decides which tools to call (search, ingest, fetch live logs) based on your question.
- **Semantic Log Search** — Logs are parsed, chunked by Lambda request ID, embedded, and stored in Qdrant for semantic similarity search.
- **Live Log Fetching** — Pull the latest logs straight from CloudWatch in real time.
- **Streaming Chat UI** — A polished Next.js frontend with real-time SSE streaming, tool execution indicators, Markdown rendering, and session management.
- **Multi-Session Support** — Create and switch between multiple analysis sessions, each with its own conversation thread.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────┐
│                   Next.js Frontend                   │
│         (React 19 · Tailwind v4 · shadcn/ui)         │
│                                                      │
│  Chat UI ←─── SSE Stream ───→ FastAPI Backend        │
└──────────────────────┬───────────────────────────────┘
                       │  POST /chat/stream
                       ▼
┌──────────────────────────────────────────────────────┐
│                   FastAPI (api.py)                    │
│                  CORS · SSE endpoint                  │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│               LangGraph Agent (agent.py)             │
│          AWS Bedrock (Amazon Nova Pro)                │
│                                                      │
│   ┌────────────┐  ┌──────────────┐  ┌─────────────┐ │
│   │ get_groups  │  │ search_qdrant│  │ fetch_live  │ │
│   └────────────┘  └──────────────┘  └─────────────┘ │
│   ┌────────────┐                                     │
│   │   ingest   │                                     │
│   └────────────┘                                     │
└──────────┬───────────────┬───────────────────────────┘
           │               │
           ▼               ▼
┌─────────────────┐ ┌─────────────────┐
│  AWS CloudWatch │ │   Qdrant (Local) │
│     Logs API    │ │  Vector Database │
└─────────────────┘ └─────────────────┘
```

---

## 📂 Project Structure

```
cloud_watch/
├── backend/
│   ├── api.py              # FastAPI server with SSE streaming endpoint
│   ├── agent.py            # LangGraph ReAct agent with tool routing
│   ├── tools.py            # Agent tools (search, ingest, fetch, list)
│   ├── log_pipeline.py     # CloudWatch log fetching, parsing & chunking
│   ├── query.py            # Standalone RAG query script (Bedrock Converse)
│   ├── rag.py              # Qdrant collection setup helper
│   └── requirements.txt    # Python dependencies
├── frontend/
│   ├── app/
│   │   ├── layout.tsx      # Root layout with theme provider
│   │   ├── page.tsx        # Main chat interface
│   │   └── globals.css     # Global styles
│   ├── components/
│   │   └── ui/             # shadcn/ui component library
│   └── package.json        # Node.js dependencies
└── README.md
```

---

## 🔧 Prerequisites

| Dependency | Version | Purpose |
|---|---|---|
| **Python** | 3.10+ | Backend runtime |
| **Node.js** | 18+ | Frontend runtime |
| **Docker** | Latest | Running Qdrant |
| **AWS CLI** | Configured | CloudWatch & Bedrock access |
| **AWS Bedrock** | Model access enabled | LLM inference (Amazon Nova Pro) |

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/Amadabh/Cloudwatch_Log_Analyzer.git
cd Cloudwatch_Log_Analyzer
```

### 2. Start Qdrant

```bash
docker run -d -p 6333:6333 -p 6334:6334 qdrant/qdrant
```

### 3. Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure AWS credentials (ensure Bedrock model access is enabled)
aws configure

# Start the API server
uvicorn api:app --reload --port 8000
```

### 4. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install
# or
pnpm install

# Start the dev server
npm run dev
```

The app will be available at **http://localhost:3000**.

---

## 🛠️ Agent Tools

The LangGraph agent has access to four tools and autonomously decides which to use:

| Tool | Description |
|---|---|
| `tool_get_log_groups` | Lists all available CloudWatch log groups in your account. |
| `tool_search_qdrant` | Performs semantic search over previously ingested logs in Qdrant. |
| `tool_ingest` | Fetches logs from CloudWatch, parses them by request ID, and stores embeddings in Qdrant. |
| `tool_fetch_live_logs` | Retrieves the latest raw logs directly from CloudWatch for real-time analysis. |

**Agent Workflow:**
1. User asks about available log groups → `tool_get_log_groups`
2. User asks about errors/events → `tool_search_qdrant` first; if empty → `tool_ingest` then retry
3. User asks for latest/real-time logs → `tool_fetch_live_logs`

---

## 💬 Example Queries

```
"What log groups are available?"
"Show me recent errors in CoverLetterGen"
"Ingest logs for /aws/lambda/CoverLetterGen"
"Fetch the latest live logs for CoverLetterGen"
"Why did my Lambda function time out?"
"What happened in request ID abc-123?"
```

---

## ⚙️ Tech Stack

### Backend
- **FastAPI** — Async API with SSE streaming
- **LangGraph** — Stateful agentic workflow with tool routing and memory
- **AWS Bedrock** — LLM inference via Amazon Nova Pro
- **Qdrant** — Vector database for semantic log search (embedding model: `BAAI/bge-small-en`)
- **Boto3** — AWS SDK for CloudWatch Logs and STS

### Frontend
- **Next.js 16** — React framework with App Router
- **React 19** — UI library
- **Tailwind CSS v4** — Utility-first styling
- **shadcn/ui** — Accessible component library (Radix UI primitives)
- **react-markdown** — Markdown rendering for agent responses
- **Lucide React** — Icon library

---

## 📄 API Reference

### `GET /`
Health check. Returns `{ "status": "ok" }`.

### `GET /session/new`
Creates a new conversation session.
**Response:** `{ "thread_id": "uuid" }`

### `POST /chat/stream`
Streams an agent response via Server-Sent Events.

**Request Body:**
```json
{
  "message": "What errors occurred in CoverLetterGen?",
  "thread_id": "uuid"
}
```

**SSE Event Types:**
| Event Type | Description |
|---|---|
| `tool_call` | Agent is calling a tool (includes tool name) |
| `tool_result` | Tool execution completed |
| `token` | Streamed text content from the agent |
| `done` | Stream complete |
| `error` | An error occurred |

---

## 🗺️ Roadmap

- [ ] User authentication (JWT + DynamoDB)
- [ ] Cross-account log access via STS AssumeRole
- [ ] CloudWatch Logs Insights query integration
- [ ] Log anomaly detection and alerting
- [ ] Persistent session storage

---

## 📝 License

This project is provided as-is for educational and personal use.
