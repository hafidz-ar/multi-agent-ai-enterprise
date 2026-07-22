# 📁 Struktur Direktori Proyek — Enterprise Multi-Agent AI Assistant

Dokumen ini berisi gambaran lengkap struktur folder dan berkas dalam proyek **Parfum Enterprise Multi-Agent System**.

```text
UAS/
├── .agents/                        # Konfigurasi & Agent Skill definitions
├── api/                            # Layer FastAPI Endpoints
│   └── main.py                     # Entry point FastAPI, CORS, & Endpoint API RESTful
├── config.py                       # Konfigurasi global (Database Path, LLM Groq, Timeout, Log Path)
├── dashboard/                      # UI Web Dashboard Enterprise
│   ├── css/                        # Custom CSS & Tailwind styles
│   ├── js/                         # Logic frontend SPA
│   │   └── app.js                  # Frontend controller (Chat, Metrics, Inventory, Procurement)
│   ├── index.html                  # Antarmuka Dashboard Enterprise Utama
│   ├── workflow_graph.html         # Visualisasi grafis alur kerja LangGraph (Interactive HTML)
│   └── workflow_graph.png          # Visualisasi alur kerja dalam format gambar
├── data/                           # Layer Penyimpanan Data System
│   ├── database/                   # SQLite Relational Database
│   │   └── parfum_enterprise.db    # Database SQLite utama (Sales, Inventory, Ingredients, POs, Catalogs)
│   ├── raw/                        # Dataset mentah CSV/TXT & FAQ SOP
│   └── vectorstore/                # ChromaDB Vector Store untuk RAG
├── logs/                           # System Logs & Audit Evaluation
│   └── evaluation.log              # Log performa, latensi, Trace ID, dan status eksekusi agen
├── parfum_agents/                  # 🤖 CORE ENGINE: Multi-Agent Architecture
│   ├── __init__.py                 # Module initializer
│   ├── business_insight_agent.py   # Agen Analisis Bisnis (Trend Sales & Margin)
│   ├── conversation_manager.py     # 🚀 Front-Door System Command Handler (reset, help, cancel, menu)
│   ├── coordinator_ai.py           # 🎓 Coordinator AI & Respon Natural Synthesis (LLM Final Formatting)
│   ├── event_bus.py                # ⚡ In-Memory Pub/Sub Event Bus Architecture (Decoupled Messaging)
│   ├── event_mapper.py             # 🎯 Enhanced Event Mapper (Priority, Strategy & Required Agents)
│   ├── inventory_service.py        # 📦 Specialist Agent: Manajemen Stok & Gudang
│   ├── memory_service.py           # 🧠 3-Tier Memory (Session Memory, Preference Memory, Knowledge Cache)
│   ├── models.py                   # 📐 Data Models, Enums, TypedDicts & Standardized AgentResult Schema
│   ├── nlu_service.py              # 🔍 5-Layer NLU Engine (Intent, Entity Recognition & Coreference)
│   ├── order_service.py            # 🛒 Specialist Agent: Pemrosesan Transaksi Penjualan
│   ├── planner_cache.py            # ⚡ In-Memory Execution Plan Cache untuk DAG Planner
│   ├── planner_service.py          # 📋 DAG Execution Planner (Parallel & Sequential Stage Planning)
│   ├── pricing_service.py          # 💰 Specialist Agent: Kalkulasi & Cek Harga Varian
│   ├── procurement_service.py      # 🏭 Specialist Agent: Reorder & Purchase Order Bahan Baku
│   ├── production_service.py       # 🧪 Specialist Agent: Formulasi & Estimasi Produksi
│   ├── reporting_service.py        # 📊 Specialist Agent: Agregasi Laporan Penjualan & Inventaris
│   ├── sales_ai.py                 # Agen Asisten Penjualan & Promosi
│   ├── workflow_manager.py         # ⚙️ FSM Workflow Manager (State Machine, Retry, Rollback, Circuit Breaker)
│   └── tools/                      # Database & Vector DB Utility Handlers
│       ├── __init__.py
│       ├── db_tools.py             # Helper SQLite query execution
│       ├── utils.py                # Logging evaluation metrics & Transaction ID Generator
│       └── vector_tools.py         # Helper RAG ChromaDB Embeddings
├── scripts/                        # Utility & Data Generator Scripts
│   ├── build_vectorstore.py        # Script indexing data FAQ/SOP ke ChromaDB
│   ├── check_api.py                # Diagnostic check API FastAPI
│   ├── check_tables.py             # Quick check SQLite tables
│   ├── generate_dataset.py         # Synthetic Dataset Generator (Only Integer Values)
│   ├── load_to_sqlite.py           # Data loader CSV → SQLite
│   ├── setup_database.py           # Database Schema Creator
│   ├── test_components.py          # Unit testing komponen individual
│   └── verify_db.py                # Verifikasi integritas data SQLite
├── tests/                          # Automated Integration Test Suite
│   ├── test_nlu.py                 # Test NLU intent & entity extraction
│   ├── test_planner.py             # Test DAG Planner & routing logic
│   ├── test_router.py              # Test routing dynamic branches
│   └── test_workflow_manager.py    # Test FSM state transitions
├── workflow/                       # LangGraph Orchestration Layer
│   ├── __init__.py
│   └── graph.py                    # Complete LangGraph StateGraph, Dynamic Routing & Parallel Branches
├── Dockerfile                      # Docker containerization configuration (Port 8000)
├── README.md                       # Dokumentasi Proyek
├── requirements.txt                # Dependensi Python (LangChain, LangGraph, FastAPI, Groq, ChromaDB)
└── visualize_graph.py              # Generator Diagram Visualisasi Workflow LangGraph
```

---

## 📌 Penjelasan Singkat Sub-Sistem Utama

### 1. `parfum_agents/` (Core Multi-Agent)
Berisi seluruh spesialisasi agen dan komponen arsitektur modern V2:
- **Front Door**: `conversation_manager.py` memproses command `reset`, `help`, `cancel` secara instan.
- **Memory**: `memory_service.py` mengelola 3-Tier Memory (*Session*, *Preference*, *Knowledge Cache*).
- **Reasoning & Planning**: `nlu_service.py` -> `event_mapper.py` -> `planner_service.py` -> `workflow_manager.py`.
- **Specialist Agents**: `inventory_service.py`, `pricing_service.py`, `production_service.py`, `procurement_service.py`, `order_service.py`, `reporting_service.py`.
- **Response Synthesis**: `coordinator_ai.py` menyintesis hasil agen terstruktur menjadi bahasa natural.

### 2. `workflow/graph.py` (LangGraph Framework)
Merupakan komposer utama (*orchestrator*) yang menghubungkan seluruh agen menjadi **StateGraph** dengan kemampuan eksekusi paralel (*concurrent branching*) untuk agen `PricingService` dan `InventoryService`.

### 3. `api/main.py` & `dashboard/`
API backend berbasis FastAPI dan antarmuka web SPA dashboard interaktif untuk memantau inventaris, transaksi penjualan, pesanan pembelian (PO), dan statistik latensi agen secara *real-time*.
