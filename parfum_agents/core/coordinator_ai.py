import os
import sys
import time
import json
import sqlite3
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config
from parfum_agents.tools.utils import log_evaluation
from parfum_agents.tools.aggregator import AgentResultAggregator
from parfum_agents.repositories.catalog_repository import CatalogRepository
from models import AgentState, ResultType, Action

def _load_prompt_template(filename: str) -> str:
    path = os.path.join(config.BASE_DIR, "prompts", filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def _get_alternative_recommendations(exclude_id: str) -> str:
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT p.name, p.brand, i.size_ml, i.quantity_available, p.price_idr
            FROM inventory i JOIN perfume_catalog p ON i.perfume_id = p.perfume_id
            WHERE i.perfume_id != ? AND i.quantity_available >= 20
            ORDER BY i.quantity_available DESC LIMIT 3
        """, (exclude_id,))
        rows = c.fetchall()
        conn.close()
        if rows:
            lines = [f"• **{r[0]}** ({r[1]}) — {r[2]}ml: ready **{r[3]} botol** (Rp {r[4]:,.0f})".replace(",", ".") for r in rows]
            return "\n".join(lines)
    except Exception:
        pass
    return "• **Tom Ford Architecto Lumiere** (50ml): ready 120 botol\n• **Gucci Magnam** (100ml): ready 90 botol"

def run(state: AgentState) -> dict:
    start_time       = time.time()
    user_input       = state.get("input", "")
    planner_status   = state.get("planner_status", "READY")
    semantic_frame   = state.get("semantic_frame", {})
    ambiguities      = semantic_frame.get("ambiguities", [])
    services_results = state.get("services_results", [])
    goal             = semantic_frame.get("goal", "UNKNOWN")
    entities         = semantic_frame.get("entities", {})

    wf_state = state.get("workflow_state", "START")
    tx_context = state.get("transaction_context", {})
    event = state.get("workflow_event", "UNKNOWN")

    # Aggregate all specialist agent results by Action Enum
    results_by_action = AgentResultAggregator.merge_results(services_results)

    if tx_context.get("workflow") == "RESTOCK":
        direct = _handle_restock_direct(state, services_results, start_time)
        if direct:
            return direct
    
    # 0. Penanganan FSM Transaction State
    if wf_state == "WAITING_USER_INPUT":
        if tx_context.get("status") == "WAITING_CONFIRMATION":
            unit_price_fmt = None
            subtotal_fmt = None
            total_avail = None
            
            product_name = tx_context.get("product", "Produk")
            size_ml = tx_context.get("size_ml", 50)
            qty = tx_context.get("qty", 1)

            pricing_data = results_by_action.get(Action.CHECK_PRICE) or results_by_action.get("PricingService") or {}
            inventory_data = results_by_action.get(Action.CHECK_STOCK) or results_by_action.get("InventoryService") or {}

            unit_price = pricing_data.get("unit_price")
            total_price = pricing_data.get("total_price") or pricing_data.get("subtotal") or (unit_price * qty if unit_price else None)
            total_avail = inventory_data.get("stock") or inventory_data.get("total_available")

            if unit_price and total_price:
                unit_price_fmt = f"Rp {unit_price:,.0f}".replace(",", ".")
                subtotal_fmt = f"Rp {total_price:,.0f}".replace(",", ".")
                msg = (
                    f"Saya menemukan produk yang Anda pilih.\n\n"
                    f"**Ringkasan Pesanan**\n"
                    f"• Produk: {product_name}\n"
                    f"• Ukuran: {size_ml}ml\n"
                    f"• Jumlah: {qty} botol\n"
                    f"• Harga satuan: {unit_price_fmt}\n"
                    f"• Subtotal: {subtotal_fmt}\n"
                    f"• Stok tersedia: {total_avail if total_avail is not None else 'Tersedia'} botol\n\n"
                    f"Apakah Anda ingin melanjutkan ke pembayaran?"
                )
            else:
                msg = f"Stok {product_name} {size_ml}ml tersedia. Apakah Anda ingin melanjutkan ke pembayaran?"

            return _respond_directly(start_time, msg)
            
        elif tx_context.get("status") == "WAITING_PAYMENT":
            return _respond_directly(start_time, "Silakan pilih metode pembayaran:\n• Tunai\n• Transfer\n• QRIS")
            
    if wf_state == "CANCELLED":
        if event == "TIMEOUT":
            return _respond_directly(start_time, "Sesi transaksi Anda telah kedaluwarsa karena tidak ada aktivitas. Silakan mulai transaksi baru.")
        elif event == "REJECT" or event == "CANCEL":
            return _respond_directly(start_time, "Baik, pesanan Anda telah dibatalkan. Ada lagi yang bisa saya bantu?")
            
    if wf_state == "COMPLETED":
        order_data = results_by_action.get(Action.CREATE_ORDER) or results_by_action.get("OrderService") or {}
        if order_data.get("success", True) and order_data.get("invoice"):
            inv_no = order_data.get("invoice") or order_data.get("transaction_id", tx_context.get("invoice_no", "INV-20260722-0001"))
            p_name = order_data.get("product", tx_context.get("product", "Parfum"))
            s_ml = order_data.get("size_ml", tx_context.get("size_ml", 50))
            q_val = order_data.get("qty", tx_context.get("qty", 1))
            u_price = order_data.get("unit_price", tx_context.get("unit_price", 0))
            tot_price = order_data.get("total_price") or order_data.get("subtotal", tx_context.get("subtotal", 0))
            pay_method = str(order_data.get("payment_method", tx_context.get("payment_method", "Tunai"))).capitalize()
            rem_stock = order_data.get("remaining_stock", tx_context.get("remaining_stock", 0))

            u_price_fmt = f"Rp {u_price:,.0f}".replace(",", ".") if u_price else "Rp 0"
            tot_price_fmt = f"Rp {tot_price:,.0f}".replace(",", ".") if tot_price else "Rp 0"

            receipt_msg = (
                f"✅ Pembelian berhasil diproses.\n\n"
                f"**Detail Transaksi**\n"
                f"• Produk: {p_name}\n"
                f"• Ukuran: {s_ml}ml\n"
                f"• Jumlah: {q_val} botol\n"
                f"• Harga satuan: {u_price_fmt}\n"
                f"• Total pembayaran: {tot_price_fmt}\n"
                f"• Metode pembayaran: {pay_method}\n"
                f"• Nomor transaksi: {inv_no}\n"
                f"• Sisa stok: {rem_stock} botol\n\n"
                f"Terima kasih telah berbelanja di Parfum Enterprise."
            )
            # Reset workflow_state after showing receipt so next query is fresh
            return {
                **_respond_directly(start_time, receipt_msg),
                "workflow_state": "START",
                "transaction_context": {}
            }
                    
        # COMPLETED but no order data (stale state) — fall through to normal processing
        wf_state = "START"
        state["workflow_state"] = "START"
        state["transaction_context"] = {}
        
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

    context = state.get("conversation_context", {})

    if goal == "GREETING":
        return _respond_directly(start_time, "Halo! Selamat datang di Parfum Enterprise AI Assistant. Ada yang bisa saya bantu terkait katalog, stok, harga, atau pembelian hari ini?")

    if goal in ["RECOMMENDATION", "CATALOG_CHECK"] or (goal == "CONFIRM" and context.get("active_recommendation")):
        return _handle_recommendation(state, user_input, start_time)

    if goal == "UNKNOWN":
        return _respond_directly(start_time,
            "Mohon maaf, saya tidak mengerti maksud Anda. 😊\n\n"
            "Saya adalah AI Assistant toko parfum. Saya bisa membantu:\n"
            "• Pembelian parfum\n"
            "• Cek harga & stok\n"
            "• Laporan penjualan\n"
            "• Restock & reorder\n\n"
            "Ketik **help** untuk panduan lengkap, atau langsung sampaikan kebutuhan Anda!"
        )

    if goal == "FAQ_FEATURE":
        if "reorder" in user_input.lower() or "restock" in user_input.lower():
            msg = (
                "💡 **Fitur Otomatis Reorder / Restock:**\n\n"
                "Ya! Sistem kami memantau ketersediaan stok secara real-time. "
                "Ketika stok suatu parfum berada di bawah ambang batas (reorder point), "
                "sistem akan mendeteksi kekurangan stok dan membantu membuatkan draf pesanan produksi/reorder."
            )
        elif "po" in user_input.lower():
            msg = (
                "📋 **Fitur Otomatis Purchase Order (PO):**\n\n"
                "Ya! Saat proses produksi membutuhkan bahan baku (Top/Heart/Base notes) "
                "yang stoknya di gudang tidak mencukupi, sistem secara otomatis menerbitkan "
                "Draf Purchase Order (PO) kepada supplier bahan baku terkait."
            )
        else:
            msg = "Sistem Parfum Enterprise dilengkapi fitur pemantauan stok otomatis, pemicu reorder produksi, dan otomatisasi PO bahan baku."
        return _respond_directly(start_time, msg)

    if goal == "INVENTORY_VALUE_CHECK":
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT COALESCE(SUM(i.quantity_available * p.price_idr), 0), COUNT(DISTINCT i.perfume_id), COALESCE(SUM(i.quantity_available), 0)
            FROM inventory i
            JOIN perfume_catalog p ON i.perfume_id = p.perfume_id
        """)
        row = c.fetchone()
        conn.close()
        tot_val = row[0] or 0
        tot_prods = row[1] or 0
        tot_items = row[2] or 0
        val_fmt = f"Rp {tot_val:,.0f}".replace(",", ".")
        msg = (
            f"💎 **Total Nilai Inventori Toko Saat Ini:**\n\n"
            f"• **Total Nilai Barang**: **{val_fmt}**\n"
            f"• **Jumlah Varian Parfum**: {tot_prods} varian\n"
            f"• **Total Stok Botol**: {tot_items:,} botol"
        )
        return _respond_directly(start_time, msg)

    if goal == "FORMULA_CHECK":
        prod = entities.get("product") or context.get("current_product") or "YSL Possimus"
        repo = CatalogRepository()
        info = repo.find_product_by_name(prod)
        if info:
            p_name = info[1]
            conn = sqlite3.connect(config.DB_PATH)
            c = conn.cursor()
            c.execute("SELECT top_notes, heart_notes, base_notes, description FROM perfume_catalog WHERE perfume_id = ?", (info[0],))
            r = c.fetchone()
            conn.close()
            if r:
                msg = (
                    f"**Piramida Notes & Formulasi — {p_name}**\n\n"
                    f"• **Top Notes**: {r[0]}\n"
                    f"• **Heart Notes**: {r[1]}\n"
                    f"• **Base Notes**: {r[2]}\n\n"
                    f"**Deskripsi**: {r[3]}"
                )
                return _respond_directly(start_time, msg)

    if goal == "LOW_STOCK_CHECK":
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT p.name, i.size_ml, i.quantity_available 
            FROM inventory i 
            JOIN perfume_catalog p ON i.perfume_id = p.perfume_id 
            WHERE i.quantity_available <= 5 ORDER BY i.quantity_available ASC
        """)
        rows = c.fetchall()
        conn.close()
        if rows:
            lines = [f"• **{r[0]}** ({r[1]}ml): sisa **{r[2]} botol**" for r in rows]
            msg = "⚠️ **Daftar Produk dengan Stok Kritis (≤ 5 botol):**\n\n" + "\n".join(lines)
        else:
            msg = "✅ Saat ini tidak ada produk dengan stok di bawah 5 botol. Seluruh stok produk di gudang aman!"
        return _respond_directly(start_time, msg)

    if goal == "PO_CHECK":
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("SELECT po_number, status, created_at, approved_by FROM purchase_orders ORDER BY created_at DESC LIMIT 5")
        rows = c.fetchall()
        conn.close()
        if rows:
            lines = [f"• **{r[0]}** — Status: **{r[1]}** (Dibuat: {r[2][:10]}, Disetujui: {r[3]})" for r in rows]
            msg = "📋 **Status Purchase Order (PO) Bahan Baku:**\n\n" + "\n".join(lines)
        else:
            msg = "📋 **Status PO**: Saat ini tidak ada Purchase Order bahan baku yang sedang berjalan."
        return _respond_directly(start_time, msg)

    if goal == "SUPPLIER_CHECK":
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("SELECT supplier_name, ingredient_name, country, price_per_unit_idr, reliability_score FROM supplier LIMIT 5")
        rows = c.fetchall()
        conn.close()
        if rows:
            lines = [f"• **{r[0]}** ({r[2]}): Supplier {r[1]} — Rp {r[3]:,.0f}/unit (Rating: {r[4]}/10)".replace(",", ".") for r in rows]
            msg = "🏢 **Daftar Supplier Bahan Baku Utama:**\n\n" + "\n".join(lines)
        else:
            msg = "🏢 Informasi supplier bahan baku dapat dikonfirmasi dari database inventori."
        return _respond_directly(start_time, msg)

    # Handle REPORT_CHECK period comparison (bulan ini vs bulan lalu)
    if goal == "REPORT_CHECK" and ("vs" in user_input.lower() or "banding" in user_input.lower()):
        from datetime import datetime, timedelta
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        today = datetime.now().date()
        curr_start = today.replace(day=1).strftime("%Y-%m-%d")
        curr_end = today.strftime("%Y-%m-%d")
        last_end_dt = today.replace(day=1) - timedelta(days=1)
        last_start_dt = last_end_dt.replace(day=1)
        last_start = last_start_dt.strftime("%Y-%m-%d")
        last_end = last_end_dt.strftime("%Y-%m-%d")

        c.execute("SELECT COUNT(*), COALESCE(SUM(quantity_sold), 0), COALESCE(SUM(total_revenue_idr), 0) FROM sales_history WHERE DATE(date) BETWEEN ? AND ?", (curr_start, curr_end))
        row_curr = c.fetchone()
        c.execute("SELECT COUNT(*), COALESCE(SUM(quantity_sold), 0), COALESCE(SUM(total_revenue_idr), 0) FROM sales_history WHERE DATE(date) BETWEEN ? AND ?", (last_start, last_end))
        row_last = c.fetchone()
        conn.close()

        rev_curr = row_curr[2] or 0
        rev_last = row_last[2] or 0
        diff = rev_curr - rev_last
        growth = ((diff / rev_last) * 100) if rev_last > 0 else 0

        rev_c_fmt = f"Rp {rev_curr:,.0f}".replace(",", ".")
        rev_l_fmt = f"Rp {rev_last:,.0f}".replace(",", ".")
        diff_fmt = f"Rp {abs(diff):,.0f}".replace(",", ".")

        growth_str = f"📈 Naik **+{growth:.1f}%** ({diff_fmt})" if diff >= 0 else f"📉 Turun **-{abs(growth):.1f}%** ({diff_fmt})"

        msg = (
            f"📊 **Perbandingan Penjualan: Bulan Ini vs Bulan Lalu**\n\n"
            f"• **Bulan Ini** ({curr_start} s/d {curr_end}):\n"
            f"  - Pendapatan: **{rev_c_fmt}** ({row_curr[0]:,} transaksi, {row_curr[1]:,} botol)\n\n"
            f"• **Bulan Lalu** ({last_start} s/d {last_end}):\n"
            f"  - Pendapatan: **{rev_l_fmt}** ({row_last[0]:,} transaksi, {row_last[1]:,} botol)\n\n"
            f"• **Pertumbuhan**: {growth_str}"
        )
        return _respond_directly(start_time, msg)



    if goal == "PURCHASE" and entities.get("product") and entities.get("size_ml") and entities.get("quantity"):
        prod = entities.get("product")
        size = entities.get("size_ml")
        qty = entities.get("quantity")
        repo = CatalogRepository()
        info = repo.find_product_by_name(prod)
        p_name = info[1] if info else prod
        p_id = info[0] if info else 'PRF-026'
        unit_price = info[3] if info else 1000000
        if size == 50:
            unit_price = int(unit_price * 0.65)
        elif size == 30:
            unit_price = int(unit_price * 0.45)
        tot_price = unit_price * qty
        tot_fmt = f"Rp {tot_price:,.0f}".replace(",", ".")

        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("SELECT quantity_available FROM inventory WHERE perfume_id = ? AND size_ml = ?", (p_id, size))
        r = c.fetchone()
        conn.close()
        stk = r[0] if r else 50

        if stk >= qty:
            msg = (
                f"Pesanan Anda untuk **{p_name}** ({size}ml, {qty} botol) siap diproses.\n\n"
                f"• Stok Tersedia: **{stk} botol**\n"
                f"• Total Harga : **{tot_fmt}**\n\n"
                f"Apakah Anda ingin melanjutkan ke konfirmasi dan pembayaran?"
            )
        else:
            alts = _get_alternative_recommendations(p_id)
            msg = (
                f"⚠️ **Stok TIDAK CUKUP** untuk pesanan {qty} botol **{p_name}** ({size}ml). "
                f"(Stok ready saat ini: **{stk} botol**).\n\n"
                f"💡 **Rekomendasi Produk Alternatif yang Stoknya Melimpah:**\n"
                f"{alts}\n\n"
                f"🔔 **Opsi Lain**: Apakah Anda ingin mengambil stok ready yang ada ({stk} botol), memilih alternatif di atas, atau mengajukan **Pre-Order / Restock Produksi** untuk {qty} botol?"
            )
        return _respond_directly(start_time, msg)

    if goal == "STOCK_CHECK":
        prod = entities.get("product") or context.get("current_product") or "YSL Possimus"
        size = entities.get("size_ml")
        req_qty = entities.get("quantity") or 1

        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        repo = CatalogRepository()
        info = repo.find_product_by_name(prod)
        p_id = info[0] if info else prod
        p_name = info[1] if info else prod

        if size:
            c.execute("""
                SELECT p.name, i.size_ml, i.quantity_available 
                FROM inventory i JOIN perfume_catalog p ON i.perfume_id = p.perfume_id 
                WHERE i.perfume_id = ? AND i.size_ml = ?
            """, (p_id, size))
        else:
            c.execute("""
                SELECT p.name, i.size_ml, i.quantity_available 
                FROM inventory i JOIN perfume_catalog p ON i.perfume_id = p.perfume_id 
                WHERE i.perfume_id = ?
            """, (p_id,))
        rows = c.fetchall()
        conn.close()

        if rows:
            lines = [f"• Ukuran {r[1]}ml: tersedia **{r[2]} botol**" for r in rows]
            lines_str = "\n".join(lines)
            total_stk = sum(r[2] for r in rows)
            if total_stk >= req_qty:
                msg = (
                    f"**Informasi Stok — {p_name}:**\n\n"
                    f"{lines_str}\n\n"
                    f"✅ **Stok CUKUP** untuk pesanan {req_qty} botol! (Total ketersediaan: **{total_stk} botol**)."
                )
            else:
                alts = _get_alternative_recommendations(p_id)
                msg = (
                    f"**Informasi Ketersediaan Stok — {p_name}:**\n\n"
                    f"{lines_str}\n\n"
                    f"⚠️ **Stok TIDAK CUKUP** untuk pesanan {req_qty} botol. (Total ketersediaan ready: **{total_stk} botol**).\n\n"
                    f"💡 **Rekomendasi Produk Alternatif yang Stoknya Melimpah:**\n"
                    f"{alts}\n\n"
                    f"🔔 **Opsi**: Apakah Anda ingin mengambil stok ready yang ada ({total_stk} botol), memilih produk alternatif di atas, atau mengajukan **Pre-Order / Restock Produksi** untuk {req_qty} botol?"
                )
            return _respond_directly(start_time, msg)

    # Handle REPORT_CHECK: build rich formatted report directly from service data
    if goal == "REPORT_CHECK" and services_results:
        report_result = next((r for r in services_results if r.get("service_name") == "ReportingService"), None)
        if report_result and report_result.get("payload"):
            return _format_report_response(report_result["payload"], start_time)

    if not services_results:
        return _handle_fallback(state, user_input, goal, entities, start_time)

    # 3. Ada service data ➔ LLM Synthesizer
    return _synthesize_with_llm(state, user_input, goal, entities, services_results, start_time)

def _handle_clarification(state, user_input, goal, entities, ambiguities, start_time):
    context = state.get("conversation_context", {})
    tx_context = state.get("transaction_context", {})

    if goal == "RESTOCK" or tx_context.get("workflow") == "RESTOCK":
        return _respond_directly(start_time, _build_restock_clarification(entities, context, tx_context, ambiguities))

    product    = entities.get("product") or context.get("current_product") or "belum diketahui"
    size_ml    = entities.get("size_ml")  or context.get("current_variant")
    quantity   = entities.get("quantity")

    if product != "belum diketahui" and not size_ml:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        repo = CatalogRepository()
        info = repo.find_product_by_name(product)
        p_id = info[0] if info else product
        p_name = info[1] if info else product
        c.execute("SELECT size_ml, quantity_available FROM inventory WHERE perfume_id = ?", (p_id,))
        rows = c.fetchall()
        conn.close()
        req_q = quantity or 1
        if rows:
            lines = [f"• Ukuran {r[0]}ml: **{r[1]} botol**" for r in rows]
            lines_str = "\n".join(lines)
            tot_stk = sum(r[1] for r in rows)
            if tot_stk >= req_q:
                msg = (
                    f"Informasi ketersediaan stok **{p_name}**:\n\n"
                    f"{lines_str}\n\n"
                    f"✅ **Stok CUKUP** untuk pesanan {req_q} botol! (Total ketersediaan: **{tot_stk} botol**).\n\n"
                    f"Silakan konfirmasi ukuran botol yang ingin Anda pesan (50ml atau 100ml)."
                )
            else:
                alts = _get_alternative_recommendations(p_id)
                msg = (
                    f"Informasi ketersediaan stok **{p_name}**:\n\n"
                    f"{lines_str}\n\n"
                    f"⚠️ **Stok TIDAK CUKUP** untuk pesanan {req_q} botol. (Total ready saat ini: **{tot_stk} botol**).\n\n"
                    f"💡 **Rekomendasi Produk Alternatif yang Stoknya Melimpah:**\n"
                    f"{alts}\n\n"
                    f"🔔 **Opsi**: Apakah Anda ingin mengambil stok ready yang ada ({tot_stk} botol), memilih produk alternatif di atas, atau mengajukan **Pre-Order / Restock Produksi** untuk {req_q} botol?"
                )
            return _respond_directly(start_time, msg)

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
        final_text = re.sub(r'^(Selamat[!\s,]+(Anda|datang)?[^\.\!\n]*[\.\!\n]*|Halo[!\s,]+[^\.\!\n]*[\.\!\n]*)', '', final_text, flags=re.IGNORECASE).strip()
        if not final_text:
            final_text = f"Mohon mengonfirmasi informasi yang ingin Anda pesan."

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

def _build_restock_clarification(entities: dict, context: dict, tx_context: dict, ambiguities: list) -> str:
    """Build a contextual clarification message for RESTOCK/REORDER goal."""
    product  = entities.get("product") or tx_context.get("product") or context.get("current_product")
    size_ml  = entities.get("size_ml") or tx_context.get("size_ml") or context.get("current_variant")
    quantity = entities.get("quantity") or tx_context.get("qty")

    if product and size_ml and not quantity:
        return (
            f"Baik, Anda ingin melakukan reorder **{product} {size_ml}ml**.\n\n"
            f"Berapa botol yang ingin diproduksi/direstock?"
        )
    if product and not size_ml:
        return (
            f"Baik, Anda ingin melakukan reorder **{product}**.\n\n"
            f"Silakan tentukan:\n"
            f"• Ukuran botol: 50ml atau 100ml\n"
            f"• Jumlah botol yang ingin diproduksi"
        )
    missing_parts = []
    if "product" in ambiguities or not product:
        missing_parts.append("nama produk parfum")
    if "size_ml" in ambiguities or not size_ml:
        missing_parts.append("ukuran botol (50ml atau 100ml)")
    if "quantity" in ambiguities or not quantity:
        missing_parts.append("jumlah botol yang ingin diproduksi")

    if missing_parts:
        return f"Untuk proses reorder, mohon konfirmasi {', '.join(missing_parts)}."
    return "Mohon berikan detail produk yang ingin di-reorder."

def _synthesize_with_llm(state, user_input, goal, entities, services_results, start_time):
    try:
        llm = ChatGroq(
            model=config.LLM_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0.4
        )
        template = _load_prompt_template("coordinator.txt") or "Kamu adalah AI Assistant toko parfum enterprise."
        
        results_str = json.dumps(services_results, indent=2)
        system_msg  = SystemMessage(content=template)
        human_msg   = HumanMessage(content=f"""Pertanyaan User: "{user_input}"
Hasil Data dari Specialist Agents:
{results_str}

Sintesiskan jawaban final yang ramah, profesional, dan to the point untuk pelanggan.""")

        response   = llm.invoke([system_msg, human_msg])
        final_text = response.content.strip()

        latency = (time.time() - start_time) * 1000
        return {
            "final_response": final_text,
            "_metrics": {
                "agent":    "CoordinatorAI",
                "latency_ms": latency,
                "decision": "Synthesize Response",
                "status":   "OK"
            }
        }
    except Exception:
        fallback_msg = services_results[0].get("user_message", "Permintaan Anda telah diproses.")
        return _respond_directly(start_time, fallback_msg)

def _handle_recommendation(state, user_input: str, start_time: float) -> dict:
    context = state.get("conversation_context", {})
    history = state.get("conversation_history", [])
    text_low = user_input.lower()

    # Direct DB query for gender-specific catalog queries (e.g. semua produk unisex, parfum pria, parfum wanita)
    gender_map = {
        "unisex": "Unisex",
        "pria": "Male",
        "laki": "Male",
        "cowok": "Male",
        "wanita": "Female",
        "perempuan": "Female",
        "cewek": "Female"
    }
    target_gen_key = next((g for g in gender_map if g in text_low), None)
    if target_gen_key:
        db_gender = gender_map[target_gen_key]
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT name, brand, category, price_idr 
            FROM perfume_catalog 
            WHERE LOWER(gender) = ? OR LOWER(gender) = ? 
            ORDER BY price_idr ASC
        """, (db_gender.lower(), target_gen_key.lower()))
        rows = c.fetchall()
        conn.close()
        if rows:
            lines = [f"{idx}. **{r[0]}** ({r[1]}) | Kategori: {r[2]} — Rp {r[3]:,.0f}".replace(",", ".") for idx, r in enumerate(rows, 1)]
            label = "Unisex" if db_gender == "Unisex" else ("Pria" if db_gender == "Male" else "Wanita")
            msg = (
                f"Berikut adalah seluruh daftar koleksi parfum **{label}** resmi di katalog toko kami:\n\n"
                + "\n".join(lines) +
                "\n\nApakah Anda tertarik untuk mengecek stok atau memesan salah satunya?"
            )
            res = _respond_directly(start_time, msg)
            res["conversation_context"] = {**context, "active_recommendation": True}
            return res

    # Direct DB query for category-specific cheapest queries (e.g. termurah kategori Floral)
    categories = ["floral", "woody", "citrus", "oriental", "fresh"]
    target_cat = next((c for c in categories if c in text_low), None)

    if target_cat and any(w in text_low for w in ["termurah", "paling murah", "murah"]):
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT name, brand, price_idr, gender, top_notes 
            FROM perfume_catalog 
            WHERE LOWER(category) = ? 
            ORDER BY price_idr ASC LIMIT 3
        """, (target_cat.lower(),))
        rows = c.fetchall()
        conn.close()
        if rows:
            cheapest = rows[0]
            p_fmt = f"Rp {cheapest[2]:,.0f}".replace(",", ".")
            lines = [f"1. **{cheapest[0]}** ({cheapest[1]}) — **{p_fmt}** (Termurah dalam kategori {target_cat.capitalize()})"]
            for idx, r in enumerate(rows[1:], 2):
                lines.append(f"{idx}. **{r[0]}** ({r[1]}) — Rp {r[2]:,.0f}".replace(",", "."))
            msg = (
                f"Parfum termurah di katalog resmi kami untuk kategori **{target_cat.capitalize()}** adalah:\n\n"
                + "\n".join(lines) +
                "\n\nApakah Anda tertarik untuk mengecek stok atau memesannya?"
            )
            res = _respond_directly(start_time, msg)
            res["conversation_context"] = {**context, "active_recommendation": True}
            return res

    repo = CatalogRepository()
    catalog_data = repo.get_catalog_summary()

    catalog_lines = []
    for item in catalog_data:
        p_val = item.get('price_idr', 0)
        p_fmt = f"Rp {p_val:,.0f}".replace(",", ".")
        name = item.get('name', '')
        brand = item.get('brand', '')
        cat = item.get('category', '')
        gen = item.get('gender', '')
        top = item.get('top_notes', '')
        heart = item.get('heart_notes', '')
        base = item.get('base_notes', '')
        catalog_lines.append(f"- {name} ({brand}) | Kategori: {cat} | Gender: {gen} | Harga 50ml: {p_fmt} | Notes: {top} (top), {heart} (heart), {base} (base)")

    catalog_text = "\n".join(catalog_lines)

    template = _load_prompt_template("recommendation.txt") or "Kamu adalah AI Assistant resmi toko Parfum Enterprise."

    system_prompt = (
        f"{template}\n\n"
        f"DAFTAR KATALOG RESMI PARFUM KAMI:\n"
        f"{catalog_text}\n\n"
        f"ATURAN MUTLAK:\n"
        f"1. Kamu HANYA BOLEH merekomendasikan produk yang ADA dalam DAFTAR KATALOG RESMI di atas.\n"
        f"2. Sebutkan nama produk, brand, dan harga resminya secara akurat sesuai data katalog.\n"
        f"3. DILARANG KERAS merekomendasikan merk luar atau membuat nama produk fiktif (seperti 'Parfum Second', 'Parfum Remaja Rp 50.000').\n"
        f"4. Jika pelanggan membalas dengan persetujuan atau kata seperti 'boleh', 'baik', 'iya', berikan rincian rekomendasi parfum unggulan dari katalog resmi kita."
    )

    try:
        llm = ChatGroq(
            model=config.LLM_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0.3
        )

        messages = [SystemMessage(content=system_prompt)]
        if history:
            for msg in list(history)[-6:]:
                r_role = msg.get("role", "user")
                c_content = msg.get("content", "")
                if r_role == "user":
                    messages.append(HumanMessage(content=c_content))
                else:
                    messages.append(SystemMessage(content=f"Jawaban kamu sebelumnya: {c_content}"))

        messages.append(HumanMessage(content=user_input))

        response = llm.invoke(messages)
        final_text = response.content.strip()
        final_text = re.sub(r'^(Selamat[!\s,]+(Anda|datang)?[^\.\!\n]*[\.\!\n]*|Halo[!\s,]+[^\.\!\n]*[\.\!\n]*)', '', final_text, flags=re.IGNORECASE).strip()

        res = _respond_directly(start_time, final_text)
        res["conversation_context"] = {**context, "active_recommendation": True}
        return res
    except Exception:
        fallback_msg = (
            "Berikut beberapa rekomendasi parfum favorit di toko kami:\n"
            "• **YSL Possimus** — Rp 2.957.500 (Aroma Woody & Elegant)\n"
            "• **Tom Ford Intense** — Rp 3.150.000 (Aroma Warm & Luxury)\n"
            "• **Le Labo Magnam Absolu** — Rp 2.177.500 (Aroma Fresh & Floral)\n\n"
            "Apakah ada yang menarik minat Anda?"
        )
        res = _respond_directly(start_time, fallback_msg)
        res["conversation_context"] = {**context, "active_recommendation": True}
        return res


def _handle_fallback(state, user_input, goal, entities, start_time):
    try:
        llm = ChatGroq(
            model=config.LLM_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0.5
        )
        system_msg = SystemMessage(content="Kamu adalah AI Assistant toko parfum yang ramah.")
        human_msg  = HumanMessage(content=user_input)

        response   = llm.invoke([system_msg, human_msg])
        final_text = response.content.strip()

        latency = (time.time() - start_time) * 1000
        return {
            "final_response": final_text,
            "_metrics": {
                "agent":    "CoordinatorAI",
                "latency_ms": latency,
                "decision": "General Chat (Fallback)",
                "status":   "OK"
            }
        }
    except Exception:
        return _respond_directly(start_time, "Ada yang bisa saya bantu lagi terkait produk parfum?")

def _respond_directly(start_time, message: str) -> dict:
    latency = (time.time() - start_time) * 1000
    return {
        "final_response": message,
        "_metrics": {
            "agent":    "CoordinatorAI",
            "latency_ms": latency,
            "decision": "Direct Response",
            "status":   "OK"
        }
    }


def _format_report_response(payload: dict, start_time: float) -> dict:
    """Build a rich, human-readable report message from ReportingService payload."""
    period     = payload.get("period", "Periode Tidak Diketahui")
    sales      = payload.get("sales", {})
    inventory  = payload.get("inventory_snapshot", {})

    total_tx       = sales.get("total_transactions", 0)
    total_qty      = sales.get("total_qty_sold", 0)
    total_rev      = sales.get("total_revenue_idr", 0)
    top_products   = sales.get("top_products", [])
    inv_value      = inventory.get("total_inventory_value", 0)
    total_stock    = inventory.get("total_stock_items", 0)
    low_stock_warn = inventory.get("low_stock_warnings", 0)

    rev_fmt = f"Rp {total_rev:,.0f}".replace(",", ".")
    inv_fmt = f"Rp {inv_value:,.0f}".replace(",", ".")

    # Top products section
    top_lines = ""
    for i, p in enumerate(top_products, 1):
        top_lines += f"  {i}. {p.get('name', '-')} — {p.get('qty_sold', 0):,} botol\n"
    if not top_lines:
        top_lines = "  (Tidak ada data penjualan)\n"

    low_stock_indicator = f"\u26a0\ufe0f {low_stock_warn} produk hampir habis" if low_stock_warn > 0 else "\u2705 Stok semua produk aman"

    separator = "\u2500" * 35
    msg = (
        f"\U0001f4ca **Laporan Penjualan \u2014 {period}**\n"
        f"{separator}\n\n"
        f"**Ringkasan Penjualan**\n"
        f"\u2022 Total transaksi  : {total_tx:,} transaksi\n"
        f"\u2022 Total terjual    : {total_qty:,} botol\n"
        f"\u2022 Total pendapatan : {rev_fmt}\n\n"
        f"**Top 3 Produk Terlaris**\n"
        f"{top_lines}\n"
        f"**Snapshot Inventori**\n"
        f"\u2022 Total stok       : {total_stock:,} botol\n"
        f"\u2022 Nilai inventori  : {inv_fmt}\n"
        f"\u2022 Status stok      : {low_stock_indicator}\n"
    )
    return _respond_directly(start_time, msg)

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
