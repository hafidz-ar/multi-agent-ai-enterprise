import os
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from workflow.graph import build_workflow

def generate_visualizations():
    print("Building LangGraph Workflow...")
    app = build_workflow()
    graph = app.get_graph()
    
    # 1. Output ASCII Representation in Terminal
    print("\n=================== GRAPH ASCII REPRESENTATION ===================")
    try:
        ascii_graph = graph.draw_ascii()
        print(ascii_graph)
    except Exception as e:
        print(f"ASCII graph skipped: {e} (Hint: 'pip install grandalf' to enable ASCII rendering)")

    DOCS_DIR = BASE_DIR / "docs"
    DASHBOARD_DIR = BASE_DIR / "dashboard"
    DOCS_DIR.mkdir(exist_ok=True)
    DASHBOARD_DIR.mkdir(exist_ok=True)

    # 2. Raw Mermaid Code from LangGraph
    raw_mermaid_code = graph.draw_mermaid()
    raw_mermaid_file = DOCS_DIR / "workflow_graph_raw.mmd"
    with open(raw_mermaid_file, "w", encoding="utf-8") as f:
        f.write(raw_mermaid_code)

    # 3. 100% Valid, Clean, Spacious & Tested 10/10 Enterprise Mermaid Syntax Diagram
    clean_mermaid_code = """---
config:
  theme: dark
  flowchart:
    curve: basis
    nodeSpacing: 80
    rankSpacing: 100
---
flowchart TD
    %% Node Definitions
    START(["🟢 USER INPUT<br/>Pesan User"])
    CM["⚡ Conversation Manager<br/>Front-Door System Commands"]
    MEM["💾 Memory Service<br/>Cross-Turn Preference Memory"]
    NLU["🧠 NLU Service<br/>Generic Entity Extraction"]
    EM["⚡ Event Mapper<br/>Intent to Event"]
    PS["📋 Planner Service<br/>Typed ExecutionPlan & Action Enums"]
    
    WM{"🔀 Workflow Manager<br/>Pure FSM State Router"}
    EE["⚙️ Execution Engine & Action Router<br/>AgentRegistry & Action Dispatcher"]

    subgraph Agents ["Tahap 2: Specialist Agents (Action Handlers)"]
        direction LR
        PRIC["🏷️ PricingAgent<br/>CHECK_PRICE (Enrichment)"]
        INV["📦 InventoryAgent<br/>CHECK_STOCK (Read Only)"]
        ORD["📝 OrderAgent<br/>CREATE_ORDER (Atomic Transaction)"]
        PROD["🧪 ProductionAgent<br/>PRODUCE_ITEM"]
        PROC["🛒 ProcurementAgent<br/>PROCURE_ITEM"]
        REP["📊 ReportingAgent<br/>CHECK_REPORT"]
    end
    
    REPO[("🗄️ Repositories Layer<br/>Catalog, Inventory, Order SQL Isolation")]
    COORD["🤖 Coordinator AI<br/>Action-Indexed Response Synthesizer"]
    END_NODE(["🔴 BOT RESPONSE<br/>Jawaban Final"])

    %% 1. Ingestion Pipeline
    subgraph Stage1 ["Tahap 1: Ingestion & Analysis Pipeline"]
        START --> CM --> MEM --> NLU --> EM --> PS --> WM
    end

    %% 2. Execution Routing
    WM --> EE
    EE -- "Action.CHECK_PRICE" --> PRIC
    EE -- "Action.CHECK_STOCK" --> INV
    EE -- "Action.CREATE_ORDER" --> ORD
    EE -- "Action.PRODUCE_ITEM" --> PROD
    EE -- "Action.PROCURE_ITEM" --> PROC
    EE -- "Action.CHECK_REPORT" --> REP

    %% 3. Persistence Isolation Layer
    PRIC --> REPO
    INV --> REPO
    ORD -- "Atomic Transaction" --> REPO
    PROD --> REPO
    PROC --> REPO

    %% 4. Response Synthesis Pipeline
    REPO --> COORD
    REP --> COORD
    COORD --> END_NODE

    %% Styling Nodes
    classDef startNode fill:#10B981,stroke:#047857,stroke-width:2px,color:#fff,font-weight:bold;
    classDef endNode fill:#EF4444,stroke:#B91C1C,stroke-width:2px,color:#fff,font-weight:bold;
    classDef router fill:#8B5CF6,stroke:#6D28D9,stroke-width:3px,color:#fff,font-weight:bold;
    classDef service fill:#1E293B,stroke:#3B82F6,stroke-width:2px,color:#93C5FD;
    classDef llm fill:#F59E0B,stroke:#D97706,stroke-width:2px,color:#FFFBEB,font-weight:bold;
    classDef ingester fill:#334155,stroke:#64748B,stroke-width:1px,color:#F8FAFC;
    classDef repo fill:#0F766E,stroke:#14B8A6,stroke-width:2px,color:#CCFBF1,font-weight:bold;

    class START startNode;
    class END_NODE endNode;
    class WM,EE router;
    class CM,MEM,NLU,EM,PS ingester;
    class PRIC,INV,ORD,REP,PROD,PROC service;
    class REPO repo;
    class COORD llm;
"""
    clean_mermaid_file = DOCS_DIR / "workflow_graph_clean.mmd"
    with open(clean_mermaid_file, "w", encoding="utf-8") as f:
        f.write(clean_mermaid_code)
    print(f"Saved Raw Mermaid Diagram: {raw_mermaid_file}")
    print(f"Saved Clean Mermaid Diagram: {clean_mermaid_file}")

    # 4. Generate Interactive Standalone HTML Document
    html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LangGraph Multi-Agent Architecture - Parfum Enterprise</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #0f172a;
            --bg-card: #1e293b;
            --accent-purple: #8b5cf6;
            --accent-blue: #3b82f6;
            --accent-green: #10b981;
            --accent-amber: #f59e0b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --border-color: #334155;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }}

        body {{
            background-color: var(--bg-primary);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            padding: 24px;
        }}

        .header {{
            background: linear-gradient(135deg, rgba(30,41,59,0.9) 0%, rgba(15,23,42,0.9) 100%);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 20px 28px;
            margin-bottom: 20px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .header-title h1 {{
            font-size: 1.6rem;
            font-weight: 700;
            background: linear-gradient(90deg, #a78bfa, #60a5fa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 4px;
        }}

        .header-title p {{
            color: var(--text-muted);
            font-size: 0.9rem;
        }}

        .main-content {{
            display: flex;
            flex-direction: column;
            gap: 20px;
            flex: 1;
        }}

        .graph-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 30px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            overflow: auto;
            position: relative;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.2);
            min-height: 880px;
            width: 100%;
        }}

        .graph-controls {{
            position: absolute;
            top: 16px;
            right: 16px;
            display: flex;
            gap: 8px;
            background: rgba(15, 23, 42, 0.88);
            backdrop-filter: blur(12px);
            padding: 6px 10px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            z-index: 10;
        }}

        .control-btn {{
            background: #334155;
            border: none;
            color: var(--text-main);
            height: 30px;
            padding: 0 10px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.85rem;
            font-weight: 600;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .control-btn:hover {{
            background: var(--accent-purple);
            color: #fff;
        }}

        .graph-overlay-left {{
            position: absolute;
            top: 16px;
            left: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            width: 310px;
            z-index: 10;
            max-height: calc(100% - 32px);
            overflow-y: auto;
        }}

        .overlay-card {{
            background: rgba(15, 23, 42, 0.88);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 14px 16px;
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.3);
        }}

        .overlay-card h3 {{
            font-size: 0.92rem;
            margin-bottom: 10px;
            color: #f1f5f9;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .legend-list {{
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 0.82rem;
        }}

        .legend-color {{
            width: 14px;
            height: 14px;
            border-radius: 4px;
            flex-shrink: 0;
        }}

        .node-desc {{
            color: var(--text-muted);
            font-size: 0.75rem;
            margin-top: 1px;
        }}

        .step-list {{
            counter-reset: step;
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        .step-item {{
            position: relative;
            padding-left: 24px;
            font-size: 0.8rem;
        }}

        .step-item::before {{
            counter-increment: step;
            content: counter(step);
            position: absolute;
            left: 0;
            top: 0;
            width: 16px;
            height: 16px;
            background: rgba(139, 92, 246, 0.25);
            color: #c4b5fd;
            border: 1px solid rgba(139, 92, 246, 0.5);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.65rem;
            font-weight: 700;
        }}

        .mermaid-wrapper {{
            width: 100%;
            height: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            overflow: auto;
            padding: 20px;
        }}

        .mermaid-wrapper .mermaid {{
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            transform-origin: center center;
            transition: transform 0.2s ease-out;
        }}

        .mermaid-wrapper svg {{
            max-width: 100% !important;
            height: auto !important;
            width: 100% !important;
            border-radius: 8px;
        }}

        @media (max-width: 1024px) {{
            .graph-overlay-left {{
                position: static;
                width: 100%;
                margin-bottom: 16px;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-title">
            <h1>LangGraph Multi-Agent Architecture</h1>
            <p>Visualisasi Action Router, Decoupled Repositories, & Execution Engine</p>
        </div>
    </div>

    <div class="main-content">
        <div class="graph-card">
            <!-- Controls (Top Right) -->
            <div class="graph-controls">
                <button class="control-btn" onclick="zoomGraph(0.15)">🔍 +</button>
                <button class="control-btn" onclick="zoomGraph(-0.15)">🔍 -</button>
                <button class="control-btn" onclick="resetZoom()">⟲ Reset</button>
            </div>

            <!-- Left Floating Cards (Top Left) -->
            <div class="graph-overlay-left">
                <div class="overlay-card">
                    <h3>📌 Keterangan Komponen</h3>
                    <ul class="legend-list">
                        <li class="legend-item">
                            <div class="legend-color" style="background: #8b5cf6;"></div>
                            <div>
                                <strong>Workflow Manager (Pure FSM)</strong>
                                <div class="node-desc">Router state tanpa dependensi agen</div>
                            </div>
                        </li>
                        <li class="legend-item">
                            <div class="legend-color" style="background: #14b8a6;"></div>
                            <div>
                                <strong>Repositories Layer</strong>
                                <div class="node-desc">Isolasi SQL (Catalog, Inventory, Order)</div>
                            </div>
                        </li>
                        <li class="legend-item">
                            <div class="legend-color" style="background: #3b82f6;"></div>
                            <div>
                                <strong>Specialist Agents (Action Handlers)</strong>
                                <div class="node-desc">BaseSpecialistAgent via Action Enum</div>
                            </div>
                        </li>
                        <li class="legend-item">
                            <div class="legend-color" style="background: #f59e0b;"></div>
                            <div>
                                <strong>Coordinator AI</strong>
                                <div class="node-desc">Action-indexed response synthesizer</div>
                            </div>
                        </li>
                    </ul>
                </div>

                <div class="overlay-card">
                    <h3>🚀 Alur Eksekusi Diagram</h3>
                    <ol class="step-list">
                        <li class="step-item">
                            <strong>Ingestion & Analysis</strong>
                            <div class="node-desc">CM ➔ Memory ➔ NLU (Generic) ➔ EventMapper ➔ Planner.</div>
                        </li>
                        <li class="step-item">
                            <strong>FSM & Action Router</strong>
                            <div class="node-desc">WorkflowManager FSM ➔ ExecutionEngine & ActionRouter.</div>
                        </li>
                        <li class="step-item">
                            <strong>Execution & Repositories</strong>
                            <div class="node-desc">Pricing & Inventory (Read-Only) ➔ Order (Atomic Write).</div>
                        </li>
                        <li class="step-item">
                            <strong>Response Synthesis</strong>
                            <div class="node-desc">Coordinator AI menyintesiskan teks jawaban ke pengguna.</div>
                        </li>
                    </ol>
                </div>
            </div>

            <!-- Mermaid Canvas -->
            <div class="mermaid-wrapper">
                <div class="mermaid" id="mermaid-element">
{clean_mermaid_code}
                </div>
            </div>
        </div>
    </div>

    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'dark',
            flowchart: {{
                useMaxWidth: true,
                htmlLabels: true,
                curve: 'basis',
                nodeSpacing: 80,
                rankSpacing: 100
            }}
        }});

        let currentZoom = 1.0;
        function zoomGraph(delta) {{
            currentZoom += delta;
            if (currentZoom < 0.4) currentZoom = 0.4;
            if (currentZoom > 2.5) currentZoom = 2.5;
            const element = document.getElementById('mermaid-element');
            element.style.transform = `scale(${{currentZoom}})`;
        }}

        function resetZoom() {{
            currentZoom = 1.0;
            const element = document.getElementById('mermaid-element');
            element.style.transform = `scale(1.0)`;
        }}
    </script>
</body>
</html>
"""
    html_file = DOCS_DIR / "workflow_graph.html"
    dashboard_html_file = DASHBOARD_DIR / "workflow_graph.html"
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    with open(dashboard_html_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Saved Interactive Clean HTML Graph: {html_file}")
    print(f"Saved Dashboard HTML Graph: {dashboard_html_file}")

if __name__ == "__main__":
    generate_visualizations()
