# 📁 Struktur Folder Proyek Enterprise — AI Parfum Assistant

Dokumen ini menjelaskan struktur folder dan modul lengkap dari proyek **Enterprise AI Parfum Assistant** yang menggunakan arsitektur Multi-Agent (Planner-Executor), LangGraph workflow, FSM resilience, 3-tier memory system, dan Event-Driven Pub/Sub architecture.

---

```text
UAS/
├── config/                      # ⚙️ Configuration Package
│   ├── __init__.py              # Package re-exports
│   ├── database.py              # Path database SQLite, ChromaDB vector store, logs
│   ├── llm.py                   # Konfigurasi LLM (Groq API, model selection, embeddings)
│   └── settings.py              # System timeout, FSM thresholds, developer flags
│
├── models/                      # 📐 Domain Schemas & Enums Package
│   ├── __init__.py              # Package re-exports
│   ├── events.py                # WorkflowEvent, WorkflowStatus, ResultType, Severity
│   ├── results.py               # ServiceResult & AgentResult TypedDicts
│   └── state.py                 # LangGraph AgentState, TransactionContext, SessionContext
│
├── prompts/                     # 📝 Externalized Prompt Templates
│   ├── coordinator.txt          # System prompt untuk CoordinatorAI
│   ├── clarification.txt        # System prompt untuk klarifikasi slot NLU
│   ├── recommendation.txt       # System prompt & aturan katalog resmi rekomendasi
│   └── sales.txt                # System prompt untuk SalesAI
│
├── parfum_agents/               # 🤖 Specialist & Orchestrator Agents Package
│   ├── __init__.py              # Top-level re-exports for 100% backward compatibility
│   ├── event_bus.py             # In-memory Pub/Sub Event Bus architecture
│   ├── models.py                # Wrapper re-export ke package models
│   ├── core/                    # 🧠 Core Agent Engine & Orchestration
│   │   ├── __init__.py
│   │   ├── conversation_manager.py # Front-door command handler (reset, help, cancel, 0ms LLM bypass)
│   │   ├── workflow_manager.py     # FSM state machine (retry, rollback, circuit breaker)
│   │   └── coordinator_ai.py       # Final response generator & catalog grounding
│   │
│   ├── memory/                  # 💾 3-Tier Memory Architecture
│   │   ├── __init__.py
│   │   └── memory_service.py       # Working session memory, preference memory, knowledge cache
│   │
│   ├── planning/                # 🗺️ Intent Mapping & DAG Execution Planning
│   │   ├── __init__.py
│   │   ├── event_mapper.py         # NLU output -> WorkflowEvent & strategy (Single vs Multi-Agent Parallel)
│   │   ├── planner_service.py      # DAG execution planner (clarification gating)
│   │   └── planner_cache.py        # In-memory execution plan cache
│   │
│   ├── nlu/                     # 🔤 Natural Language Understanding Engine
│   │   ├── __init__.py
│   │   └── nlu_service.py          # 5-Layer NLU engine (Slot-filling, coref, rules, LLM fallback)
│   │
│   ├── services/                # 🛠️ Business Domain Specialist Services
│   │   ├── __init__.py
│   │   ├── inventory_service.py    # Stock check & reorder point validation
│   │   ├── pricing_service.py      # Price check & size calculation
│   │   ├── procurement_service.py  # Purchase order (PO) generation & supplier lookup
│   │   ├── production_service.py   # Work order (WO) generation & ingredient ledger
│   │   ├── reporting_service.py    # Sales history analytics & period-filtered report
│   │   └── order_service.py        # Transaction execution & inventory deduction
│   │
│   ├── business/                # 💼 Business Intelligence & Sales Agents
│   │   ├── __init__.py
│   │   ├── sales_ai.py             # Structured intent & entity extraction
│   │   └── business_insight_agent.py # Executive summary & analytics insights
│   │
│   └── tools/                   # 🔧 Utility Tools & Data Access
│       ├── __init__.py
│       ├── db_tools.py             # Raw SQL helpers
│       ├── vector_tools.py         # Chroma VectorDB retrieval tools
│       └── utils.py                # Transaction ID generator & evaluation logging
│
├── workflow/                    # 🔄 Workflow Orchestration Engine
│   ├── graph.py                 # LangGraph StateGraph pipeline, parallel branch execution, tracing
│   └── visualize_graph.py       # Generator visualisasi diagram workflow (HTML, MMD, PNG)
│
├── api/                         # 🌐 FastAPI REST API Service
│   └── main.py                  # API Endpoints (/api/chat, /api/events/history, /api/planner/cache)
│
├── dashboard/                   # 🖥️ Enterprise Web Dashboard
│   ├── index.html               # Multi-Agent Web Interface
│   ├── styles.css               # Modern dark-mode glassmorphism styling
│   └── app.js                   # Live event stream, metric gauges, and chat UI logic
│
├── data/                        # 🗄️ Database & Storage Layer
│   ├── dataset.sqlite           # SQLite enterprise database
│   ├── chroma_db/               # ChromaDB vector embedding store
│   ├── processed/               # Placeholders for ETL processed dataset files
│   └── exports/                 # Placeholders for generated report exports
│
├── docs/                        # 📚 Architecture & System Documentation
│   └── .gitkeep
│
├── config.py                    # Root config wrapper (re-exports from config package)
├── direktori.md                 # Dokumentasi struktur direktori proyek
└── requirements.txt             # Dependency list
```

---

## 🌟 Highlight Keunggulan Arsitektur:
1. **Modul Terpisah & Jelas (Separation of Concerns)**: Setiap domain memiliki direktori khusus (`core`, `memory`, `planning`, `nlu`, `services`, `business`).
2. **Backward Compatibility**: Subpackage `__init__.py` dan root `config.py` menjamin 100% kompatibilitas impor lama maupun baru.
3. **0ms Command Latency**: `conversation_manager.py` menangani perintah `/reset`, `/help`, `/cancel` secara langsung tanpa membuang token LLM.
4. **Resilient FSM**: `workflow_manager.py` mengelola *Circuit Breaker*, *Rollback*, dan *Transaction Timeout*.
5. **Parallel DAG Execution**: `graph.py` dan `planner_service.py` mendukung eksekusi parallel LangGraph untuk efisiensi latensi.
6. **Workflow Visualizer**: `workflow/visualize_graph.py` memproduksi diagram visual interaktif LangGraph (Mermaid MMD, HTML, PNG).
