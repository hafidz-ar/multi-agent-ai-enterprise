import os
import sys
import time
import json
import sqlite3
import re
from datetime import datetime, timedelta
from langchain_groq import ChatGroq

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from parfum_agents.tools.utils import log_evaluation
from parfum_agents.models import AgentState

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CONTEXT_WINDOW = 8          # last N messages sent to LLM
SUMMARY_THRESHOLD = 50      # start summarising after this many messages
CONFIDENCE_THRESHOLD = 0.60 # min confidence before asking for clarification

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_perfume_catalog():
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("SELECT name FROM perfume_catalog")
        names = [r[0] for r in c.fetchall()]
        conn.close()
        return names
    except:
        return []


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(state: AgentState) -> dict:
    start_time = time.time()
    input_text  = state.get("input", "")
    conv_ctx    = state.get("conversation_context", {})
    tx_ctx      = state.get("transaction_context", {})
    resolved    = state.get("resolved_entities", {})
    pending     = state.get("pending_slot", "")
    history     = state.get("conversation_history", [])
    catalog     = get_perfume_catalog()

    def _wrap(frame: dict) -> dict:
        frame["_metrics"] = {
            "agent":      "NLUService",
            "latency_ms": (time.time() - start_time) * 1000,
            "decision":   frame.get("goal", "UNKNOWN"),
            "status":     "OK"
        }
        return {"semantic_frame": frame}

    # ------------------------------------------------------------------ #
    # Layer 0 — Active workflow context lock (highest priority)            #
    # ------------------------------------------------------------------ #
    locked = _semantic_frame_from_active_context(input_text, conv_ctx, tx_ctx)
    if locked:
        _update_resolved_entities(locked, resolved)
        return {**_wrap(locked), "resolved_entities": resolved}

    # ------------------------------------------------------------------ #
    # Layer 1 — Pending slot filling (deterministic, no LLM)              #
    # ------------------------------------------------------------------ #
    if pending:
        slot_frame = _fill_pending_slot(input_text, pending, resolved, conv_ctx, catalog)
        if slot_frame:
            _update_resolved_entities(slot_frame, resolved)
            return {**_wrap(slot_frame), "resolved_entities": resolved, "pending_slot": ""}

    # ------------------------------------------------------------------ #
    # Layer 2 — Deterministic coreference resolver (no LLM)               #
    # ------------------------------------------------------------------ #
    coref_frame = _deterministic_coreref_resolver(input_text, resolved, conv_ctx, catalog)
    if coref_frame:
        _update_resolved_entities(coref_frame, resolved)
        return {**_wrap(coref_frame), "resolved_entities": resolved}

    # ------------------------------------------------------------------ #
    # Layer 3 — Rule-based extraction                                      #
    # ------------------------------------------------------------------ #
    rule_frame = _semantic_frame_from_rules(input_text, catalog)
    if rule_frame:
        _update_resolved_entities(rule_frame, resolved)
        return {**_wrap(rule_frame), "resolved_entities": resolved}

    # ------------------------------------------------------------------ #
    # Layer 4 — LLM fallback (only when rules cannot determine intent)     #
    # ------------------------------------------------------------------ #
    llm_frame = _llm_fallback(input_text, conv_ctx, tx_ctx, resolved, history, catalog, start_time)
    if llm_frame:
        _update_resolved_entities(llm_frame, resolved)
        return {**_wrap(llm_frame), "resolved_entities": resolved}

    # ------------------------------------------------------------------ #
    # Layer 5 — Hard fallback                                              #
    # ------------------------------------------------------------------ #
    fallback = {
        "goal": "UNKNOWN",
        "entities": {"product": None, "size_ml": None, "quantity": None, "period": None, "payment_method": None},
        "requested_operations": [],
        "confidence": 0.0,
        "ambiguities": []
    }
    return {**_wrap(fallback), "resolved_entities": resolved}


# ---------------------------------------------------------------------------
# Layer 0 — Active workflow context lock (unchanged from original)
# ---------------------------------------------------------------------------

def _semantic_frame_from_active_context(input_text: str, conv_ctx: dict, tx_ctx: dict):
    active_wf  = tx_ctx.get("workflow") or conv_ctx.get("active_workflow") or conv_ctx.get("conversation_goal")
    tx_status  = tx_ctx.get("status")
    stripped   = input_text.strip().lower()
    number_match = re.fullmatch(r"(\d+)\s*(pcs?|piece|botol|unit)?", stripped)

    if active_wf == "RESTOCK" and tx_status == "WAITING_PROCUREMENT_CONFIRMATION":
        if stripped in {"ya", "iya", "ok", "oke", "lanjut", "gas", "setuju"}:
            return _make_frame("CONFIRM",  intent="CONFIRM_PROCUREMENT")
        if stripped in {"tidak", "nggak", "ga", "batal", "cancel"}:
            return _make_frame("REJECT",   intent="REJECT_PROCUREMENT")

    if active_wf == "RESTOCK" and tx_status in {"WAITING_QTY", "DRAFT", "COLLECTING_INFORMATION"} and number_match:
        qty = int(number_match.group(1))
        return {
            "goal": "RESTOCK",
            "entities": {
                "product":         tx_ctx.get("product") or conv_ctx.get("current_product"),
                "size_ml":         tx_ctx.get("size_ml") or conv_ctx.get("current_variant"),
                "quantity":        qty,
                "period":          None,
                "payment_method":  None
            },
            "requested_operations": ["CHECK_STOCK", "PRODUCE_ITEM"],
            "confidence": 0.99,
            "ambiguities": []
        }

    return None


# ---------------------------------------------------------------------------
# Layer 1 — Pending slot filling
# ---------------------------------------------------------------------------

def _fill_pending_slot(input_text: str, pending: str, resolved: dict, conv_ctx: dict, catalog: list):
    """
    When a specific slot is being awaited, try to extract it directly.
    Returns a semantic frame if successful, else None.
    """
    text     = input_text.strip().lower()
    goal     = conv_ctx.get("conversation_goal") or resolved.get("last_goal") or "PURCHASE"
    product  = resolved.get("last_product") or conv_ctx.get("current_product")
    size_ml  = resolved.get("last_variant")  or conv_ctx.get("current_variant")

    if pending == "size_ml":
        size = _extract_size_ml(text)
        if size:
            return _make_purchase_or_goal_frame(goal, product, size, None, catalog)

        # "yang besar" / "yang kecil" shortcuts
        if any(w in text for w in ["besar", "large", "gede"]):
            return _make_purchase_or_goal_frame(goal, product, 100, None, catalog)
        if any(w in text for w in ["kecil", "small"]):
            return _make_purchase_or_goal_frame(goal, product, 50, None, catalog)

    elif pending == "quantity":
        qty = _extract_quantity(text)
        if qty is None:
            # bare number
            m = re.search(r"\b(\d+)\b", text)
            qty = int(m.group(1)) if m else None
        # word numbers
        word_map = {"satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5,
                    "enam": 6, "tujuh": 7, "delapan": 8, "sembilan": 9, "sepuluh": 10}
        for word, num in word_map.items():
            if word in text:
                qty = num
                break
        if qty:
            return _make_purchase_or_goal_frame(goal, product, size_ml, qty, catalog)

    elif pending == "product":
        prod = _extract_product_from_catalog(text, catalog)
        if prod:
            return _make_purchase_or_goal_frame(goal, prod, size_ml, None, catalog)

    elif pending == "period":
        period_data = _extract_period_with_range(text)
        if period_data:
            frame = _make_frame("REPORT_CHECK", intent="CHECK_REPORT",
                                ops=["CHECK_REPORT"])
            frame["entities"]["period"]     = period_data["label"]
            frame["entities"]["start_date"] = period_data["start_date"]
            frame["entities"]["end_date"]   = period_data["end_date"]
            return frame

    return None


def _make_purchase_or_goal_frame(goal: str, product, size_ml, quantity, catalog: list):
    """Build frame for PURCHASE / PRICE_CHECK / STOCK_CHECK using resolved entities."""
    ambiguities = []

    # Validate product
    if product:
        matched = _match_product_to_catalog(product, catalog)
        if matched:
            product = matched
        else:
            product = "UNKNOWN_PRODUCT"
            ambiguities.append("product")
    else:
        ambiguities.append("product")

    if goal in ["PURCHASE", "RESTOCK"] and not size_ml:
        ambiguities.append("size_ml")
    if goal == "RESTOCK" and not quantity:
        ambiguities.append("quantity")

    ops_map = {
        "PURCHASE":   ["CHECK_STOCK"],
        "PRICE_CHECK":["CHECK_PRICE"],
        "STOCK_CHECK":["CHECK_STOCK"],
        "RESTOCK":    ["CHECK_STOCK", "PRODUCE_ITEM", "PROCURE_ITEM"],
    }
    return {
        "goal": goal,
        "intent": _intent_for_goal(goal, ""),
        "entities": {
            "product":        product,
            "size_ml":        size_ml,
            "quantity":       quantity if quantity else (1 if goal == "PURCHASE" else None),
            "period":         None,
            "payment_method": None
        },
        "requested_operations": ops_map.get(goal, ["CHECK_STOCK"]),
        "confidence": 0.97,
        "ambiguities": ambiguities
    }


# ---------------------------------------------------------------------------
# Layer 2 — Deterministic coreference resolver
# ---------------------------------------------------------------------------

# Patterns that signal a reference to a previously discussed entity
_COREF_PRODUCT_PATTERNS = [
    r"\byang\s+itu\b", r"\byang\s+tadi\b", r"\bitu\b", r"\btadi\b",
    r"\byang\s+sama\b", r"\bproduk\s+yang\s+sama\b"
]
_SIZE_SHORTCUTS = {
    "besar": 100, "large": 100, "gede": 100,
    "kecil": 50,  "small": 50,  "mini": 30
}


def _deterministic_coreref_resolver(input_text: str, resolved: dict, conv_ctx: dict, catalog: list):
    """
    Resolve references like 'yang itu', 'berapa harganya?', 'yang 50ml', 'stoknya'
    using resolved_entities + conversation_context WITHOUT calling an LLM.
    Returns a semantic frame or None.
    """
    text    = input_text.strip().lower()
    product = resolved.get("last_product") or conv_ctx.get("current_product")
    size_ml = resolved.get("last_variant")  or conv_ctx.get("current_variant")
    goal    = conv_ctx.get("conversation_goal")

    # ── 1. Bare size-only input (e.g. "yang 50ml", "100ml saja") ──────────
    size_only = _extract_size_ml(text)
    has_product_in_text = bool(_extract_product_from_catalog(text, catalog))
    if size_only and not has_product_in_text and product:
        # inherit goal or use PRICE_CHECK / PURCHASE heuristic
        inferred_goal = goal if goal in ["PURCHASE", "PRICE_CHECK", "STOCK_CHECK", "RESTOCK"] else "PRICE_CHECK"
        return _make_purchase_or_goal_frame(inferred_goal, product, size_only, None, catalog)

    # ── 2. "Yang itu / yang tadi / itu" — co-reference product ────────────
    has_coref = any(re.search(p, text) for p in _COREF_PRODUCT_PATTERNS)
    if has_coref and product:
        override_size = _extract_size_ml(text) or size_ml
        for key, val in _SIZE_SHORTCUTS.items():
            if key in text:
                override_size = val
                break
        inferred_goal = goal if goal in ["PURCHASE", "PRICE_CHECK", "STOCK_CHECK", "RESTOCK"] else "PRICE_CHECK"
        return _make_purchase_or_goal_frame(inferred_goal, product, override_size, None, catalog)

    # ── 3. "Berapa harganya?" / "harganya?" — PRICE_CHECK with known product ──
    price_q_patterns = [r"\bharganya\b", r"\bberapa harga\b", r"\bharga(?:nya)?\b"]
    if product and any(re.search(p, text) for p in price_q_patterns) and not has_product_in_text:
        override_size = _extract_size_ml(text) or size_ml
        return _make_purchase_or_goal_frame("PRICE_CHECK", product, override_size, None, catalog)

    # ── 4. "Stoknya?" / "ada stoknya?" — STOCK_CHECK with known product ───
    stock_q_patterns = [r"\bstoknya\b", r"\bstok(?:nya)?\s+ada\b", r"\bada\s+stok\b"]
    if product and any(re.search(p, text) for p in stock_q_patterns) and not has_product_in_text:
        override_size = _extract_size_ml(text) or size_ml
        return _make_purchase_or_goal_frame("STOCK_CHECK", product, override_size, None, catalog)

    # ── 5. "Beli / saya mau beli / oke lanjut beli" with known product ────
    buy_patterns = [r"\bbeli\b", r"\border\b", r"\bpesan\b", r"\blanjut\s+beli\b", r"\boke\s+beli\b"]
    if product and any(re.search(p, text) for p in buy_patterns) and not has_product_in_text:
        override_size = _extract_size_ml(text) or size_ml
        qty = _extract_quantity(text)
        ambigs = []
        if not override_size: ambigs.append("size_ml")
        if not qty: ambigs.append("quantity")
        return {
            "goal": "PURCHASE",
            "intent": "BUY_PRODUCT",
            "entities": {
                "product": product, "size_ml": override_size,
                "quantity": qty or 1, "period": None, "payment_method": None
            },
            "requested_operations": ["CHECK_STOCK"],
            "confidence": 0.95,
            "ambiguities": ambigs
        }

    # ── 6. "Yang besar" / "yang kecil" size shortcuts with known product ──
    for key, val in _SIZE_SHORTCUTS.items():
        if key in text and product:
            inferred_goal = goal if goal in ["PURCHASE", "PRICE_CHECK", "STOCK_CHECK"] else "PRICE_CHECK"
            return _make_purchase_or_goal_frame(inferred_goal, product, val, None, catalog)

    # ── 7. Bare number where PURCHASE is the last known goal ──────────────
    if goal == "PURCHASE":
        number_match = re.fullmatch(r"\s*(\d+)\s*(pcs?|piece|botol|unit)?\s*", text)
        if number_match:
            qty = int(number_match.group(1))
            if qty < 1000:   # sanity: avoid treating size_ml as qty
                return _make_purchase_or_goal_frame("PURCHASE", product, size_ml, qty, catalog)

    # ── 8. "Kemarin?" / "bulan lalu?" where last goal = REPORT_CHECK ──────
    if goal == "REPORT_CHECK":
        period_data = _extract_period_with_range(text)
        if period_data:
            frame = _make_frame("REPORT_CHECK", intent="CHECK_REPORT", ops=["CHECK_REPORT"])
            frame["entities"]["period"]     = period_data["label"]
            frame["entities"]["start_date"] = period_data["start_date"]
            frame["entities"]["end_date"]   = period_data["end_date"]
            return frame

    return None


# ---------------------------------------------------------------------------
# Layer 3 — Rule-based extraction (unchanged logic, enhanced)
# ---------------------------------------------------------------------------

def _semantic_frame_from_rules(input_text: str, catalog: list):
    text = input_text.lower()
    goal = None

    if any(w in text for w in ["reorder", "restock", "restok", "produksi", "tambah stok", "buat stok", "order stok", "pesan stok", "stock masuk", "stok baru", "supply", "pengiriman", "stock in", "masuk barang"]):
        goal = "RESTOCK"
    elif any(w in text for w in ["cek harga", "harga", "harganya", "berapa harga", "harga berapa", "seberapa mahal", "harga barang", "bandingkan harga"]):
        goal = "PRICE_CHECK"
    elif any(w in text for w in ["cek stok", "stok", "stock", "ada stok", "stok berapa", "berapa stok", "ketersediaan", "ada gak", "masih ada", "ready", "tersedia"]):
        goal = "STOCK_CHECK"
    elif any(w in text for w in ["laporan", "report", "rekap", "penjualan", "sales", "omset", "statistik", "ringkasan", "berapa terjual"]):
        goal = "REPORT_CHECK"
    elif any(w in text for w in ["beli", "pesan", "order", "saya mau", "mau beli", "beli dong", "saya ingin", "ambil", "checkout", "transaksi"]):
        goal = "PURCHASE"
    elif any(w in text for w in ["halo", "hai", "selamat", "hi", "hei", "assalamualaikum", "pagi", "siang", "sore", "malam"]):
        goal = "GREETING"
    elif any(w in text for w in ["iya", "ya", "ok", "oke", "lanjut", "gas", "sip", "betul", "benar", "setuju", "baik", "yes", "ayo"]):
        goal = "CONFIRM"
    elif any(w in text for w in ["tidak", "batal", "ga jadi", "cancel", "nggak", "gak mau", "jangan", "enggak", "tidak jadi", "skip", "lewat"]):
        goal = "REJECT"
    elif any(w in text for w in ["tunai", "cash", "transfer", "bca", "qris", "gopay", "ovo", "mandiri", "shopeepay", "linkaja", "bri", "rekening", "cicilan"]):
        goal = "PAYMENT_METHOD"
    elif any(w in text for w in ["terima kasih", "makasih", "thanks", "thank you", "tq", "thx", "trims"]):
        goal = "GRATITUDE"
    elif any(w in text for w in ["bantuan", "help", "bisa apa", "fitur", "apa saja", "apa aja", "cara pakai", "panduan", "tutorial"]):
        goal = "HELP"
    elif any(w in text for w in ["rekomendasi", "recommend", "suggest", "saran", "cocok untuk", "parfum untuk", "parfum pria", "parfum wanita", "parfum unisex"]):
        goal = "RECOMMENDATION"
    elif any(w in text for w in ["katalog", "daftar parfum", "list parfum", "semua parfum", "produk apa saja", "koleksi"]):
        goal = "CATALOG_CHECK"

    if not goal:
        return None

    product    = _extract_product_from_catalog(text, catalog)
    size_ml    = _extract_size_ml(text)
    quantity   = _extract_quantity(text)
    period_data = _extract_period_with_range(text)
    payment    = _extract_payment(text)
    ambiguities = []

    if goal in ["PURCHASE", "RESTOCK"]:
        if not product:     ambiguities.append("product")
        if not size_ml:     ambiguities.append("size_ml")
    if goal == "RESTOCK" and not quantity:
        ambiguities.append("quantity")
    if goal == "REPORT_CHECK" and not period_data:
        ambiguities.append("period")

    entities = {
        "product":        product,
        "size_ml":        size_ml,
        "quantity":       quantity if quantity else (1 if goal == "PURCHASE" else None),
        "period":         period_data["label"] if period_data else None,
        "start_date":     period_data["start_date"] if period_data else None,
        "end_date":       period_data["end_date"] if period_data else None,
        "payment_method": payment,
    }

    return {
        "goal": goal,
        "intent": _intent_for_goal(goal, text),
        "entities": entities,
        "requested_operations": {
            "PURCHASE":    ["CHECK_STOCK"],
            "PRICE_CHECK": ["CHECK_PRICE"],
            "STOCK_CHECK": ["CHECK_STOCK"],
            "REPORT_CHECK":["CHECK_REPORT"],
            "RESTOCK":     ["CHECK_STOCK", "PRODUCE_ITEM"],
        }.get(goal, []),
        "confidence": 0.95,
        "ambiguities": ambiguities
    }


# ---------------------------------------------------------------------------
# Layer 4 — LLM fallback
# ---------------------------------------------------------------------------

def _llm_fallback(input_text, conv_ctx, tx_ctx, resolved, history, catalog, start_time):
    try:
        llm = ChatGroq(
            model=config.LLM_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0.0
        ).bind(response_format={"type": "json_object"})

        history_str = _build_history_prompt(history, limit=CONTEXT_WINDOW)

        system_prompt = f"""Kamu adalah NLU (Natural Language Understanding) Service untuk toko parfum. Output HANYA JSON, tidak ada teks lain.

Daftar Parfum Valid: {', '.join(catalog)}

═══════════════════════════════════════════
RIWAYAT PERCAKAPAN ({CONTEXT_WINDOW} pesan terakhir):
{history_str if history_str else "Belum ada riwayat."}

KONTEKS TERSTRUKTUR:
- Tujuan terakhir (goal)  : {conv_ctx.get("conversation_goal", "Tidak ada")}
- Produk terakhir         : {resolved.get("last_product") or conv_ctx.get("current_product", "Tidak ada")}
- Ukuran terakhir         : {resolved.get("last_variant")  or conv_ctx.get("current_variant",  "Tidak ada")}
- Period terakhir         : {resolved.get("last_period",  "Tidak ada")}
═══════════════════════════════════════════

ATURAN PEMETAAN GOAL:
| goal           | requested_operations                                    |
|----------------|---------------------------------------------------------|
| PURCHASE       | ["CHECK_STOCK"]                                         |
| PRICE_CHECK    | ["CHECK_PRICE"]                                         |
| STOCK_CHECK    | ["CHECK_STOCK"]                                         |
| REPORT_CHECK   | ["CHECK_REPORT"]                                        |
| RESTOCK        | ["CHECK_STOCK", "PRODUCE_ITEM", "PROCURE_ITEM"]         |
| GREETING       | []                                                      |
| CONFIRM        | []                                                      |
| REJECT         | []                                                      |
| PAYMENT_METHOD | []                                                      |
| UNKNOWN        | []                                                      |

ATURAN RESOLUSI KONTEKS (PENTING!):
1. Jika user menyebut ukuran saja (misal "50ml", "yang 100ml") dan ada produk terakhir di konteks → gunakan produk terakhir.
2. Jika user menyebut "yang itu", "itu", "tadi" → gunakan produk + ukuran dari konteks.
3. Jika user menanya harga/stok tanpa produk → gunakan produk dari konteks.
4. Jika user mengetik angka saja (misal "2", "3 botol") dan goal sebelumnya PURCHASE/RESTOCK → itu adalah quantity.
5. Jika user mengetik "lanjut", "oke", "ya" setelah penawaran → CONFIRM.

EKSTRAKSI ENTITAS:
- period: "hari ini", "kemarin", "minggu ini", "bulan ini", "tahun ini", "minggu lalu", "bulan lalu" (jika ada kata waktu)
- payment_method: "tunai", "transfer", "qris", "gopay", "ovo"

AMBIGUITIES — wajib diisi HANYA jika:
- goal=PURCHASE dan product belum ada (dan tidak ada di konteks) → tambah "product"
- goal=PURCHASE dan size_ml belum ada dan tidak bisa diinfer → tambah "size_ml"
- goal=REPORT_CHECK dan period belum ada → tambah "period"

Input User: "{input_text}"

Format output JSON:
{{
  "goal": "...",
  "intent": "...",
  "entities": {{"product": null, "size_ml": null, "quantity": null, "period": null, "payment_method": null}},
  "requested_operations": [],
  "confidence": 0.95,
  "ambiguities": []
}}
"""
        response = None
        for attempt in range(3):
            try:
                response = llm.invoke(system_prompt)
                break
            except Exception as e:
                if ("429" in str(e) or "rate" in str(e).lower()) and attempt < 2:
                    time.sleep(3)
                else:
                    raise e

        semantic_frame = json.loads(response.content)

        # ── Post-processing validation ──────────────────────────────────
        ambiguities = semantic_frame.setdefault("ambiguities", [])
        entities    = semantic_frame.setdefault("entities", {})
        goal        = semantic_frame.get("goal", "UNKNOWN")

        _apply_context_lock(input_text, semantic_frame, conv_ctx, tx_ctx)
        entities = semantic_frame.setdefault("entities", {})
        goal     = semantic_frame.get("goal", "UNKNOWN")

        # Product validation against catalog
        product = entities.get("product")
        if product:
            matched = _match_product_to_catalog(product, catalog)
            if matched:
                entities["product"] = matched
            else:
                entities["product"] = "UNKNOWN_PRODUCT"
                if "product" not in ambiguities:
                    ambiguities.append("product")

        # Mandatory field validation
        if goal in ["PURCHASE", "RESTOCK"] and (not entities.get("product") or entities.get("product") == "UNKNOWN_PRODUCT"):
            if "product" not in ambiguities:
                ambiguities.append("product")
        if goal in ["PURCHASE", "RESTOCK"] and not entities.get("size_ml"):
            if "size_ml" not in ambiguities:
                ambiguities.append("size_ml")
        if goal == "RESTOCK" and not entities.get("quantity"):
            if "quantity" not in ambiguities:
                ambiguities.append("quantity")
        if goal == "REPORT_CHECK" and not entities.get("period"):
            if "period" not in ambiguities:
                ambiguities.append("period")

        # Enrich period with date range if not yet set
        if entities.get("period") and not entities.get("start_date"):
            period_data = _extract_period_with_range(entities["period"])
            if period_data:
                entities["start_date"] = period_data["start_date"]
                entities["end_date"]   = period_data["end_date"]

        semantic_frame["ambiguities"] = ambiguities
        return semantic_frame

    except Exception as e:
        return {
            "goal": "ERROR",
            "error": str(e),
            "entities": {},
            "requested_operations": [],
            "confidence": 0.0,
            "ambiguities": []
        }


# ---------------------------------------------------------------------------
# Helpers — entity extraction
# ---------------------------------------------------------------------------

def _extract_product_from_catalog(text: str, catalog: list):
    compact = re.sub(r"[^a-z0-9]+", " ", text).strip()
    # Exact substring match first
    for product in catalog:
        if product.lower() in compact:
            return product
    # Token overlap (≥ 2 tokens)
    text_tokens = set(compact.split())
    best_match, best_score = None, 0
    for product in catalog:
        product_tokens = set(product.lower().split())
        score = len(product_tokens & text_tokens)
        if score > best_score:
            best_match, best_score = product, score
    return best_match if best_score >= 2 else None


def _match_product_to_catalog(product: str, catalog: list):
    for p in catalog:
        if p.lower() in product.lower() or product.lower() in p.lower():
            return p
    return None


def _extract_size_ml(text: str):
    match = re.search(r"\b(\d{2,3})\s*ml\b", text)
    return int(match.group(1)) if match else None


def _extract_quantity(text: str):
    match = re.search(r"\b(\d+)\s*(pcs?|piece|botol|unit)\b", text)
    return int(match.group(1)) if match else None


def _extract_payment(text: str):
    for method in ["tunai", "cash", "transfer", "bca", "qris", "gopay", "ovo", "mandiri"]:
        if method in text:
            return method
    return None


def _extract_period_with_range(text: str) -> dict | None:
    """
    Maps natural language time expressions to a label + ISO date range.
    Returns dict with keys: label, start_date, end_date (YYYY-MM-DD strings)
    or None if not matched.
    Auto-adjusts to data year if current year has no data.
    """
    today = datetime.now().date()
    
    # Auto-detect data year from DB
    try:
        import sqlite3
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("SELECT MAX(date) FROM sales_history")
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            max_date = datetime.strptime(row[0][:10], "%Y-%m-%d").date()
            if max_date.year != today.year:
                today = max_date  # Use data's latest date as reference
    except Exception:
        pass

    def iso(d):
        return d.strftime("%Y-%m-%d")

    mappings = [
        # Daily
        (["hari ini", "today"],
         "hari ini", today, today),
        (["kemarin", "yesterday"],
         "kemarin", today - timedelta(days=1), today - timedelta(days=1)),
        (["lusa"],
         "lusa", today - timedelta(days=2), today - timedelta(days=2)),
        # Weekly
        (["minggu ini", "this week"],
         "minggu ini",
         today - timedelta(days=today.weekday()),
         today - timedelta(days=today.weekday()) + timedelta(days=6)),
        (["minggu lalu", "pekan lalu", "last week"],
         "minggu lalu",
         today - timedelta(days=today.weekday() + 7),
         today - timedelta(days=today.weekday() + 1)),
        # Monthly
        (["bulan ini", "this month"],
         "bulan ini",
         today.replace(day=1),
         today),
        (["bulan lalu", "last month"],
         "bulan lalu",
         (today.replace(day=1) - timedelta(days=1)).replace(day=1),
         today.replace(day=1) - timedelta(days=1)),
        (["awal bulan"],
         "awal bulan",
         today.replace(day=1),
         today.replace(day=10)),
        (["akhir bulan"],
         "akhir bulan",
         today.replace(day=21),
         today),
        # Quarterly / yearly labels (no precise range; just label)
        (["triwulan lalu", "q1", "q2", "q3", "q4", "kuartal lalu"],
         "triwulan lalu", None, None),
        (["semester lalu", "semester ini"],
         "semester lalu", None, None),
        # Yearly
        (["tahun ini", "this year"],
         "tahun ini",
         today.replace(month=1, day=1),
         today),
        (["tahun lalu", "last year"],
         "tahun lalu",
         today.replace(year=today.year - 1, month=1, day=1),
         today.replace(year=today.year - 1, month=12, day=31)),
    ]

    for keywords, label, start, end in mappings:
        if any(kw in text for kw in keywords):
            return {
                "label":      label,
                "start_date": iso(start) if start else None,
                "end_date":   iso(end)   if end   else None
            }
    return None


# ---------------------------------------------------------------------------
# Helpers — conversation history
# ---------------------------------------------------------------------------

def _build_history_prompt(history: list, limit: int = CONTEXT_WINDOW) -> str:
    """
    Convert the last `limit` messages from conversation_history into a
    clean USER/ASSISTANT format for inclusion in the LLM prompt.
    """
    if not history:
        return ""

    recent = list(history)[-limit:]
    lines  = ["Conversation History:"]
    for msg in recent:
        role    = msg.get("role", "user").upper()
        content = msg.get("content", "").strip()
        lines.append(f"\n{role}:\n{content}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers — context / entity update
# ---------------------------------------------------------------------------

def _update_resolved_entities(frame: dict, resolved: dict):
    """Persist extracted entities into the cross-turn resolved_entities store."""
    entities = frame.get("entities", {})
    if entities.get("product") and entities["product"] != "UNKNOWN_PRODUCT":
        resolved["last_product"] = entities["product"]
    if entities.get("size_ml"):
        resolved["last_variant"] = entities["size_ml"]
    if entities.get("period"):
        resolved["last_period"] = entities["period"]
    if entities.get("payment_method"):
        resolved["last_payment"] = entities["payment_method"]
    goal = frame.get("goal")
    if goal and goal not in ["UNKNOWN", "ERROR"]:
        resolved["last_goal"] = goal


def _apply_context_lock(input_text: str, semantic_frame: dict, conv_ctx: dict, tx_ctx: dict):
    active_wf = tx_ctx.get("workflow") or conv_ctx.get("active_workflow")
    if active_wf != "RESTOCK" or tx_ctx.get("status") in {"COMPLETED", "CANCELLED", "FAILED"}:
        return

    entities = semantic_frame.setdefault("entities", {})
    if tx_ctx.get("product") or conv_ctx.get("current_product"):
        entities["product"] = tx_ctx.get("product") or conv_ctx.get("current_product")
    if tx_ctx.get("size_ml") or conv_ctx.get("current_variant"):
        entities["size_ml"] = tx_ctx.get("size_ml") or conv_ctx.get("current_variant")

    number_match = re.fullmatch(r"\s*(\d+)\s*(pcs?|piece|botol|unit)?\s*", input_text.lower())
    if number_match and tx_ctx.get("status") == "WAITING_QTY":
        entities["quantity"] = int(number_match.group(1))

    if semantic_frame.get("goal") in {"UNKNOWN", "PURCHASE", "BUY_PRODUCT"}:
        semantic_frame["goal"]                = "RESTOCK"
        semantic_frame["intent"]              = "REORDER_PRODUCT"
        semantic_frame["requested_operations"]= ["CHECK_STOCK", "PRODUCE_ITEM"]


# ---------------------------------------------------------------------------
# Helpers — misc
# ---------------------------------------------------------------------------

def _make_frame(goal: str, intent: str = "", ops: list = None, confidence: float = 0.99):
    return {
        "goal": goal,
        "intent": intent or goal,
        "entities": {"product": None, "size_ml": None, "quantity": None, "period": None, "payment_method": None},
        "requested_operations": ops or [],
        "confidence": confidence,
        "ambiguities": []
    }


def _intent_for_goal(goal: str, text: str):
    if goal == "RESTOCK":
        return "REORDER_PRODUCT" if "reorder" in text else "RESTOCK_PRODUCT"
    if goal == "PURCHASE":    return "BUY_PRODUCT"
    if goal == "STOCK_CHECK": return "CHECK_STOCK"
    if goal == "PRICE_CHECK": return "CHECK_PRICE"
    if goal == "REPORT_CHECK":return "REPORT_CHECK"
    return goal
