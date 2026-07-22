import os
import sys
import time
import json
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config
from models import AgentState, ResultType
from parfum_agents.nlu.nlu_service import _build_history_prompt

COORDINATOR_CONTEXT_WINDOW = 8  # last N history messages included in LLM context

def _load_prompt_template(filename: str) -> str:
    prompt_path = os.path.join(config.BASE_DIR, "prompts", filename)
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

def run(state: AgentState) -> dict:
    start_time = time.time()

    user_input       = state.get("input", "")
    services_results = state.get("services_results", [])
    planner_status   = state.get("planner_status", "")
    semantic_frame   = state.get("semantic_frame", {})
    ambiguities      = semantic_frame.get("ambiguities", [])
    goal             = semantic_frame.get("goal", "UNKNOWN")
    entities         = semantic_frame.get("entities", {})

    wf_state = state.get("workflow_state", "START")
    tx_context = state.get("transaction_context", {})
    event = state.get("workflow_event", "UNKNOWN")

    if tx_context.get("workflow") == "RESTOCK":
        direct = _handle_restock_direct(state, services_results, start_time)
        if direct:
            return direct
    
    # 0. Penanganan FSM Transaction State
    if wf_state == "WAITING_USER_INPUT":
        if tx_context.get("status") == "WAITING_CONFIRMATION":
            inv_msg = None
            for res in services_results:
                if res.get("service_name") == "InventoryService" and res.get("user_message"):
                    inv_msg = res.get("user_message")
            
            if not inv_msg:
                product = tx_context.get("product", "Produk")
                size = tx_context.get("size_ml", "")
                qty = tx_context.get("qty", 1)
                size_str = f" {size}ml" if size else ""
                inv_msg = f"Stok {product}{size_str} sebanyak {qty} pcs tersedia."
                
            return _respond_directly(start_time, f"{inv_msg} Apakah Anda ingin melanjutkan pembelian?")
            
        elif tx_context.get("status") == "WAITING_PAYMENT":
            return _respond_directly(start_time, "Baik, silakan pilih metode pembayaran (misal: Tunai, Transfer, atau QRIS).")
            
    if wf_state == "CANCELLED":
        if event == "TIMEOUT":
            return _respond_directly(start_time, "Sesi transaksi Anda telah kedaluwarsa karena tidak ada aktivitas. Silakan mulai transaksi baru.")
        elif event == "REJECT" or event == "CANCEL":
            return _respond_directly(start_time, "Baik, pesanan Anda telah dibatalkan. Ada lagi yang bisa saya bantu?")
            
    if wf_state == "COMPLETED":
        order_success = False
        for res in services_results:
            if res.get("service_name") == "OrderService" and res.get("result_type") == ResultType.SUCCESS:
                order_success = True
                if res.get("user_message"):
                    return _respond_directly(start_time, res["user_message"])
                    
        if order_success:
            return _respond_directly(start_time, "Pesanan Anda berhasil dibuat dan status transaksi selesai.")
        
    # 1. Khusus CLARIFICATION_REQUIRED
    if planner_status == "CLARIFICATION_REQUIRED":
        return _handle_clarification(
            state, user_input, goal, entities, ambiguities, start_time
        )

    # 2. Tidak ada service data
    if goal == "GRATITUDE":
        return _respond_directly(start_time, "Sama-sama! Senang bisa membantu Anda. Jika ada pertanyaan lain seputar parfum, jangan ragu untuk bertanya ya! 😊")
    
    if goal == "HELP":
        return _respond_directly(start_time, 
            "Berikut hal-hal yang bisa saya bantu:\n\n"
            "🛒 **Pembelian** — \"Beli Chanel Noir 50ml\"\n"
            "💰 **Cek Harga** — \"Berapa harga YSL Ratione Noir?\"\n"
            "📦 **Cek Stok** — \"Stok Tom Ford Intense ada?\"\n"
            "📊 **Laporan Penjualan** — \"Laporan bulan ini\"\n"
            "🔄 **Restock/Reorder** — \"Restok Tom Ford Intense 50ml 50 botol\"\n"
            "🎯 **Rekomendasi** — \"Rekomendasi parfum untuk pria\"\n\n"
            "Silakan ketik pertanyaan Anda!"
        )

    if not services_results:
        return _handle_no_service(state, user_input, goal, ambiguities, start_time)

    # 3. Bangun data aman untuk LLM
    safe_service_data = [
        {
            "service": s.get("service_name"),
            "status": s.get("result_type") or ("SUCCESS" if s.get("success") else "ERROR"),
            "message": s.get("user_message"),
            "data": s.get("data") if "data" in s else s.get("payload")
        }
        for s in services_results
    ]

    try:
        llm = ChatGroq(
            model=config.LLM_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0.3
        )

        history     = state.get("conversation_history", [])
        history_str = _build_history_prompt(history, limit=COORDINATOR_CONTEXT_WINDOW)
        prompt_content = _load_prompt_template("coordinator.txt") or """Kamu adalah asisten toko parfum yang profesional. Jawab pertanyaan berdasarkan DATA TRANSAKSI."""

        system_msg = SystemMessage(content=prompt_content)
        data_str = json.dumps(safe_service_data, indent=2, ensure_ascii=False)
        ambiguities_str = f"Informasi yang masih kurang dari pelanggan: {ambiguities}" if ambiguities else ""
        goal_str = f"Tujuan pelanggan: {goal}"

        history_section = f"\nRiwayat Percakapan:\n{history_str}\n" if history_str else ""
        human_msg = HumanMessage(content=f"""Pertanyaan pelanggan: "{user_input}"
{goal_str}
{history_section}
Data dari sistem:
{data_str}

{ambiguities_str}

Jawab pertanyaan pelanggan di atas berdasarkan data dari sistem. Sesuaikan nada dengan tujuan pelanggan.""")

        response = llm.invoke([system_msg, human_msg])
        final_text = response.content.strip()

        latency = (time.time() - start_time) * 1000
        return {
            "final_response": final_text,
            "_metrics": {
                "agent": "CoordinatorAI",
                "latency_ms": latency,
                "decision": "Respond User",
                "status": "OK"
            }
        }

    except Exception as e:
        latency = (time.time() - start_time) * 1000
        return {
            "final_response": f"Maaf, saat ini sistem sedang mengalami gangguan. Error: {str(e)}",
            "_metrics": {
                "agent": "CoordinatorAI",
                "latency_ms": latency,
                "decision": "Error (LLM Crash)",
                "status": "ERROR"
            }
        }

def _get_catalog_context_for_prompt():
    try:
        import sqlite3
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("SELECT name, brand, category, gender, price_idr FROM perfume_catalog ORDER BY brand ASC LIMIT 25")
        rows = c.fetchall()
        conn.close()
        lines = []
        for r in rows:
            lines.append(f"- {r[0]} (Brand: {r[1]}, Kategori: {r[2]}, Gender: {r[3]}, Rp{r[4]:,})")
        return "\n".join(lines)
    except Exception:
        return "- Tom Ford Itaque Intense\n- YSL Est Aqua\n- Chanel Hic Noir\n- Dior Architecto Noir\n- Le Labo Porro Noir"

def _handle_no_service(state, user_input, goal, ambiguities, start_time):
    conv_ctx    = state.get("conversation_context", {})
    has_greeted = conv_ctx.get("has_greeted", False)
    history     = state.get("conversation_history", [])
    history_str = _build_history_prompt(history, limit=COORDINATOR_CONTEXT_WINDOW)
    catalog_str = _get_catalog_context_for_prompt()

    try:
        llm = ChatGroq(
            model=config.LLM_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0.3
        )
        greeting_rule = (
            "Jangan memulai dengan sapaan 'Halo' atau 'Selamat datang' "
            "karena pelanggan sudah pernah disambut sebelumnya."
            if has_greeted else
            "Sambut pelanggan dengan hangat dan wajar sebagai AI Assistant resmi Parfum Enterprise."
        )
        history_section = f"\nRiwayat Percakapan:\n{history_str}" if history_str else ""
        template = _load_prompt_template("recommendation.txt") or ""

        system_msg = SystemMessage(content=f"""Kamu adalah AI Assistant resmi toko Parfum Enterprise.
{greeting_rule}

BATASAN DAN ATURAN SISTEM KETAT:
1. KATALOG RESMI PARFUM ENTERPRISE:
{catalog_str}

{template}""")

        human_msg = HumanMessage(content=f"Pelanggan berkata: \"{user_input}\"{history_section}")

        response   = llm.invoke([system_msg, human_msg])
        final_text = response.content.strip()

        latency = (time.time() - start_time) * 1000
        return {
            "final_response": final_text,
            "_metrics": {
                "agent":    "CoordinatorAI",
                "latency_ms": latency,
                "decision": "Greeting/General",
                "status":   "OK"
            }
        }

    except Exception:
        latency = (time.time() - start_time) * 1000
        fallback = (
            "Ada lagi yang bisa saya bantu? Saya bisa cek harga, stok parfum, atau membuat laporan penjualan."
            if has_greeted else
            "Halo! Ada yang bisa saya bantu hari ini? Saya bisa membantu cek harga, stok parfum, atau membuat laporan penjualan."
        )
        return {
            "final_response": fallback,
            "_metrics": {
                "agent":    "CoordinatorAI",
                "latency_ms": latency,
                "decision": "Greeting (Fallback)",
                "status":   "OK"
            }
        }

def _handle_clarification(state, user_input, goal, entities, ambiguities, start_time):
    context = state.get("conversation_context", {})
    tx_context = state.get("transaction_context", {})

    if goal == "RESTOCK" or tx_context.get("workflow") == "RESTOCK":
        return _respond_directly(start_time, _build_restock_clarification(entities, context, tx_context, ambiguities))

    product    = entities.get("product") or context.get("current_product") or "belum diketahui"
    size_ml    = entities.get("size_ml")  or context.get("current_variant")
    quantity   = entities.get("quantity")

    if product != "belum diketahui" and size_ml and ("quantity" in ambiguities or not quantity):
        return _respond_directly(start_time, f"Stok {product} {size_ml}ml tersedia. Berapa botol/pcs yang ingin Anda beli sebelum melanjutkan ke pembayaran?")

    missing_info = []
    if "product" in ambiguities:
        missing_info.append("nama produk parfum")
    if "size_ml" in ambiguities:
        missing_info.append("ukuran botol (misalnya: 50ml atau 100ml)")
    if "quantity" in ambiguities:
        missing_info.append("jumlah/banyaknya botol yang ingin dibeli")

    try:
        llm = ChatGroq(
            model=config.LLM_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0.3
        )
        template = _load_prompt_template("clarification.txt") or "Kamu adalah asisten toko parfum yang profesional."

        system_msg = SystemMessage(content=template)
        human_msg = HumanMessage(content=f"""Pelanggan ingin melakukan pembelian.
Informasi yang belum lengkap: {', '.join(missing_info)}
Tanyakan informasi ini kepada pelanggan secara sopan.""")

        response   = llm.invoke([system_msg, human_msg])
        final_text = response.content.strip()

        latency = (time.time() - start_time) * 1000
        return {
            "final_response": final_text,
            "_metrics": {
                "agent":    "CoordinatorAI",
                "latency_ms": latency,
                "decision": "Ask Clarification",
                "status":   "OK"
            }
        }
    except Exception:
        missing_str = ", ".join(missing_info) if missing_info else "informasi tambahan"
        latency = (time.time() - start_time) * 1000
        return {
            "final_response": f"Mohon maaf, bolehkan Anda mengonfirmasi {missing_str} yang ingin Anda beli?",
            "_metrics": {
                "agent":    "CoordinatorAI",
                "latency_ms": latency,
                "decision": "Ask Clarification (Fallback)",
                "status":   "OK"
            }
        }

def _handle_restock_direct(state: AgentState, services_results: list, start_time: float) -> dict | None:
    tx_context = state.get("transaction_context", {})
    status = tx_context.get("status")

    if status == "WAITING_PROCUREMENT_CONFIRMATION":
        missing_ing = tx_context.get("missing_ingredients", [])
        prod_name   = tx_context.get("product", "parfum")
        size_ml     = tx_context.get("size_ml", "")
        qty         = tx_context.get("qty", 1)

        ing_lines = []
        for item in missing_ing:
            name  = item.get("ingredient_name", item.get("ingredient_id", ""))
            short = item.get("shortage", 0)
            unit  = item.get("unit", "unit")
            ing_lines.append(f"- Bahan **{name}** kurang **{short:.2f} {unit}**")

        ing_text = "\n".join(ing_lines) if ing_lines else "- Ada bahan baku yang kurang"
        size_str = f" {size_ml}ml" if size_ml else ""

        msg = (
            f"Proses reorder **{prod_name}{size_str}** sebanyak **{qty} botol** telah divalidasi.\n\n"
            f"**Status Stok & Bahan Baku:**\n"
            f"- Stok saat ini: **0 botol** (produksi diperlukan)\n"
            f"{ing_text}\n\n"
            f"Saya dapat langsung membuat **Purchase Order (PO)** untuk bahan baku agar produksi dapat dimulai. "
            f"Apakah Anda ingin melanjutkan?"
        )
        return _respond_directly(start_time, msg)

    if status == "PROCUREMENT_APPROVED":
        prod_name = tx_context.get("product", "parfum")
        size_ml   = tx_context.get("size_ml", "")
        qty       = tx_context.get("qty", 1)
        po_count  = tx_context.get("po_count", 1)
        size_str  = f" {size_ml}ml" if size_ml else ""

        msg = (
            f"Proses reorder **{prod_name}{size_str}** sebanyak **{qty} botol** sudah dijalankan. "
            f"Telah dibuat **{po_count} pesanan pembelian (PO)** untuk bahan baku yang kurang."
        )
        return _respond_directly(start_time, msg)

    return None

def _build_restock_clarification(entities: dict, context: dict, tx_context: dict, ambiguities: list) -> str:
    product = entities.get("product") or tx_context.get("product") or context.get("current_product")
    size_ml = entities.get("size_ml") or tx_context.get("size_ml") or context.get("current_variant")
    qty     = entities.get("quantity") or tx_context.get("qty") or context.get("current_quantity")

    if not product or product == "UNKNOWN_PRODUCT":
        return "Untuk proses reorder/restok, produk parfum mana yang ingin Anda restok?"

    if not size_ml:
        return f"Untuk reorder **{product}**, ukuran botol berapa ml yang ingin direstok (misal: 30ml, 50ml, atau 100ml)?"

    if not qty or "quantity" in ambiguities or tx_context.get("status") == "WAITING_QTY":
        return f"Untuk reorder **{product} {size_ml}ml**, berapa pcs/botol yang ingin diproduksi?"

    return f"Mohon konfirmasi kembali detail restok untuk **{product} {size_ml}ml**."

def _respond_directly(start_time: float, message: str) -> dict:
    latency = (time.time() - start_time) * 1000
    return {
        "final_response": message,
        "_metrics": {
            "agent":      "CoordinatorAI",
            "latency_ms": latency,
            "decision":   "Direct Dynamic Response",
            "status":     "OK"
        }
    }
