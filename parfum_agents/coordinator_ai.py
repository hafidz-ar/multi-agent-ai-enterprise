import os
import sys
import time
import json
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from parfum_agents.models import AgentState, ResultType
from parfum_agents.nlu_service import _build_history_prompt

COORDINATOR_CONTEXT_WINDOW = 8  # last N history messages included in LLM context

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
    
    # ------------------------------------------------------------------ #
    # 0. Penanganan FSM Transaction State                                #
    # ------------------------------------------------------------------ #
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
        # Let LLM handle other cancellations (e.g. out of stock)
            
    if wf_state == "COMPLETED":
        # Extract message from OrderService result if exists
        order_success = False
        for res in services_results:
            if res.get("service_name") == "OrderService" and res.get("result_type") == ResultType.SUCCESS:
                order_success = True
                if res.get("user_message"):
                    return _respond_directly(start_time, res["user_message"])
                    
        if order_success:
            return _respond_directly(start_time, "Pesanan Anda berhasil dibuat dan status transaksi selesai.")
        # Let LLM handle other completions
        
    # ------------------------------------------------------------------ #
    # 1. Khusus CLARIFICATION_REQUIRED — jangan fallback ke "Halo!"      #
    # ------------------------------------------------------------------ #
    if planner_status == "CLARIFICATION_REQUIRED":
        return _handle_clarification(
            state, user_input, goal, entities, ambiguities, start_time
        )

    # ------------------------------------------------------------------ #
    # 2. Tidak ada service data — bisa karena GREETING / UNKNOWN intent   #
    #    Atau GRATITUDE / HELP / RECOMMENDATION / CATALOG_CHECK            #
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # 3. Bangun data aman untuk LLM                                        #
    # ------------------------------------------------------------------ #
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

        system_msg = SystemMessage(content="""Kamu adalah asisten toko parfum yang profesional.
Kamu HARUS menjawab pertanyaan pelanggan berdasarkan DATA TRANSAKSI yang diberikan.

ATURAN KETAT:
1. Jika data transaksi berisi informasi (harga, stok, laporan, dsb), sampaikan ISI DATA tersebut secara langsung dan ramah.
2. Jangan pernah memulai jawaban dengan menyapa ulang ("Halo", "Selamat datang") jika sudah ada data transaksi.
3. Jika ada ambiguities (informasi yang masih kurang), tanyakan dengan sopan dan spesifik.
4. Jika status service adalah ERROR, sampaikan pesan error-nya dengan sopan.
5. Gunakan bahasa Indonesia yang hangat, langsung ke intinya, dan hindari kata-kata teknis.
6. DILARANG menyebutkan: "Planner", "Service", "JSON", "Execution", "system", "API".
7. Gunakan riwayat percakapan untuk menjaga kesinambungan — jangan menanyakan info yang sudah diberikan pelanggan.

PANDUAN NADA BERDASARKAN TUJUAN PELANGGAN:
- PURCHASE + stok tersedia  → Nada positif, konfirmasi stok ada, tanyakan apakah mau lanjut beli.
- PURCHASE + stok kosong    → Nada empati, sampaikan stok habis, tawarkan alternatif.
- RESTOCK                   → Sampaikan status proses produksi/pembelian dari data dengan jelas dan terperinci.
- PRICE_CHECK               → Langsung sebutkan harga tanpa basa-basi.
- STOCK_CHECK               → Langsung sebutkan status stok.
- REPORT_CHECK              → Ringkas data laporan dengan poin-poin utama.""")

        data_str = json.dumps(safe_service_data, indent=2, ensure_ascii=False)
        ambiguities_str = f"Informasi yang masih kurang dari pelanggan: {ambiguities}" if ambiguities else ""
        goal_str = f"Tujuan pelanggan: {goal}"

        history_section = f"""
Riwayat Percakapan:
{history_str}
""" if history_str else ""

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
    """
    Dipanggil ketika tidak ada ServiceResult — misalnya GREETING, RECOMMENDATION, atau UNKNOWN.
    HANYA boleh merekomendasikan/membahas produk yang ada dalam sistem database.
    """
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

        system_msg = SystemMessage(content=f"""Kamu adalah AI Assistant resmi toko Parfum Enterprise.
{greeting_rule}

BATASAN DAN ATURAN SISTEM KETAT:
1. KATALOG RESMI PARFUM ENTERPRISE:
{catalog_str}

2. JIKA PELANGGAN MEMINTA REKOMENDASI ATAU MENANYAKAN PRODUK:
   - Kamu HANYA BOLEH merekomendasikan atau menyebutkan produk yang ADA DALAM DAFTAR KATALOG RESMI DI ATAS.
   - DILARANG KERAS merekomendasikan atau menyebutkan merk/produk luar di luar katalog sistem (seperti Baccarat Rouge, Dior Sauvage, Bleu de Chanel, Creed Aventus, Axe, dsb).
3. JIKA PELANGGAN MENANYAKAN TOPIK DI LUAR TOKO PARFUM (misal olahraga, politik, cuaca, masakan, dsb):
   - Sampaikan dengan sopan bahwa kamu adalah AI Assistant Parfum Enterprise dan berikan bantuan seputar layanan toko parfum kami (cek harga, cek stok, laporan, dan rekomendasi parfum dari katalog kami).
4. Gunakan bahasa Indonesia yang hangat, profesional, langsung pada intinya, dan hindari kata-kata teknis (seperti JSON, API, Service, Database).""")

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
    """
    Khusus untuk kasus CLARIFICATION_REQUIRED.
    LLM diberi tahu produk apa yang sudah dikenali dan informasi apa yang masih kurang.
    Dengan ini LLM TIDAK akan mengira produk tidak ada di sistem.
    """
    context = state.get("conversation_context", {})
    tx_context = state.get("transaction_context", {})

    if goal == "RESTOCK" or tx_context.get("workflow") == "RESTOCK":
        return _respond_directly(start_time, _build_restock_clarification(entities, context, tx_context, ambiguities))

    # Produk yang sudah dikenali (dari NLU atau konteks sesi sebelumnya)
    product    = entities.get("product") or context.get("current_product") or "belum diketahui"
    size_ml    = entities.get("size_ml")  or context.get("current_variant")
    quantity   = entities.get("quantity") or 1

    # Bangun konteks yang jelas untuk LLM
    known_info = []
    if product and product != "belum diketahui":
        known_info.append(f"Produk: {product}")
    if size_ml:
        known_info.append(f"Ukuran: {size_ml}ml")
    if quantity:
        known_info.append(f"Jumlah: {quantity}")

    missing_info = []
    if "product" in ambiguities:
        missing_info.append("nama produk parfum")
    if "size_ml" in ambiguities:
        missing_info.append("ukuran botol (misalnya: 50ml atau 100ml)")

    try:
        llm = ChatGroq(
            model=config.LLM_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0.3
        )

        system_msg = SystemMessage(content="""Kamu adalah asisten toko parfum yang profesional.
Tugas kamu adalah menanyakan informasi yang masih kurang dari pelanggan secara sopan dan spesifik.
JANGAN mengatakan produk tidak ada atau tidak ditemukan — produk SUDAH dikenali, hanya informasinya yang belum lengkap.
Gunakan bahasa Indonesia yang hangat dan langsung ke intinya.""")

        human_msg = HumanMessage(content=f"""Pelanggan ingin melakukan pembelian.

Informasi yang sudah diketahui:
{chr(10).join(known_info) if known_info else "Belum ada informasi produk"}

Informasi yang masih diperlukan:
{chr(10).join(f"- {m}" for m in missing_info) if missing_info else "Tidak ada"}

Pesan pelanggan: "{user_input}"

Tanyakan informasi yang masih diperlukan dengan sopan dan spesifik. Jangan tanyakan informasi yang sudah ada.""")

        response = llm.invoke([system_msg, human_msg])
        final_text = response.content.strip()

        latency = (time.time() - start_time) * 1000
        return {
            "final_response": final_text,
            "_metrics": {
                "agent": "CoordinatorAI",
                "latency_ms": latency,
                "decision": "Clarification Request",
                "status": "OK"
            }
        }

    except Exception as e:
        latency = (time.time() - start_time) * 1000
        return {
            "final_response": "Untuk melanjutkan pembelian, mohon sebutkan ukuran botol yang Anda inginkan (50ml atau 100ml).",
            "_metrics": {
                "agent": "CoordinatorAI",
                "latency_ms": latency,
                "decision": "Clarification (Fallback)",
                "status": "OK"
            }
        }

def _respond_directly(start_time, message):
    latency = (time.time() - start_time) * 1000
    return {
        "final_response": message,
        "_metrics": {
            "agent": "CoordinatorAI",
            "latency_ms": latency,
            "decision": "FSM_Direct_Response",
            "status": "OK"
        }
    }

def _handle_restock_direct(state, services_results, start_time):
    tx_context = state.get("transaction_context", {})
    status = tx_context.get("status")
    if state.get("planner_status") == "CLARIFICATION_REQUIRED" or status in {"WAITING_QTY", "COLLECTING_INFORMATION"}:
        semantic_frame = state.get("semantic_frame", {})
        return _respond_directly(
            start_time,
            _build_restock_clarification(
                semantic_frame.get("entities", {}),
                state.get("conversation_context", {}),
                tx_context,
                semantic_frame.get("ambiguities", [])
            )
        )

    if status == "WAITING_PROCUREMENT_CONFIRMATION":
        return _respond_directly(start_time, _build_procurement_confirmation(state, services_results, tx_context))

    if status == "CANCELLED":
        return _respond_directly(start_time, "Baik, proses reorder saya batalkan. Tidak ada Purchase Order yang dibuat.")

    if not services_results:
        return None

    messages = [
        res.get("user_message")
        for res in services_results
        if res.get("user_message")
    ]
    if not messages:
        if tx_context.get("status") in {"COMPLETED", "PROCUREMENT_APPROVED"}:
            messages = ["Purchase Order berhasil dibuat dan proses pengadaan bahan baku telah dimulai."]
        else:
            return None

    product = tx_context.get("product")
    size_ml = tx_context.get("size_ml")
    qty = tx_context.get("qty")
    header = "Proses reorder sudah dijalankan"
    if product and size_ml and qty:
        header = f"Proses reorder {product} {size_ml}ml sebanyak {qty} pcs sudah dijalankan"

    return _respond_directly(start_time, header + ". " + " ".join(messages))

def _build_procurement_confirmation(state, services_results, tx_context):
    product = tx_context.get("product", "produk tersebut")
    size_ml = tx_context.get("size_ml")
    qty = tx_context.get("qty")
    pending = tx_context.get("pending_procurement", [])

    stock_line = _inventory_summary_line(services_results)
    missing_line = _missing_ingredients_line(pending)

    intro = f"Baik. Saya sudah memvalidasi reorder {product}"
    if size_ml and qty:
        intro += f" {size_ml}ml sebanyak {qty} botol"
    intro += "."

    return (
        f"{intro}\n\n"
        f"Hasil pengecekan:\n"
        f"- {stock_line}\n"
        f"- Produksi diperlukan: Ya\n"
        f"- {missing_line}\n\n"
        "Saya dapat langsung membuat Purchase Order untuk bahan baku agar produksi dapat dimulai. Apakah Anda ingin melanjutkan?"
    )

def _inventory_summary_line(services_results):
    for res in services_results:
        if res.get("service_name") == "InventoryService":
            payload = res.get("payload", {})
            total = payload.get("total_available")
            if total is not None:
                return f"Stok saat ini: {total} botol"
    return "Stok saat ini sudah dicek"

def _missing_ingredients_line(missing):
    if not missing:
        return "Bahan baku mencukupi"

    first = missing[0]
    ingredient = first.get("ingredient_name", "bahan baku")
    shortage = first.get("shortage", 0)
    unit = "unit"
    if isinstance(shortage, float) and shortage.is_integer():
        shortage = int(shortage)

    suffix = ""
    if len(missing) > 1:
        suffix = f" dan {len(missing) - 1} bahan lain"

    return f"Bahan baku {ingredient} kurang {shortage} {unit}{suffix}"

def _build_restock_clarification(entities, context, tx_context, ambiguities):
    product = entities.get("product") or tx_context.get("product") or context.get("current_product")
    size_ml = entities.get("size_ml") or tx_context.get("size_ml") or context.get("current_variant")
    qty = entities.get("quantity") or tx_context.get("qty") or context.get("current_quantity")
    missing = set(ambiguities)

    if (not product or product == "UNKNOWN_PRODUCT") or "product" in missing:
        return "Produk parfum apa yang ingin direorder?"
    if not size_ml or "size_ml" in missing:
        return f"Untuk reorder {product}, ukuran botol berapa ml?"
    if not qty or "quantity" in missing:
        return f"Berapa jumlah botol yang ingin Anda reorder untuk {product} {size_ml}ml?"
    return f"Baik, saya proses reorder {product} {size_ml}ml sebanyak {qty} pcs."
