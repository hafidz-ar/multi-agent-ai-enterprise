import os
import sys
import time
import json
import sqlite3
import re
from datetime import datetime, timedelta
from langchain_groq import ChatGroq

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config
from parfum_agents.tools.utils import log_evaluation
from models import AgentState

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
# Generic Unified Entity Extractor
# ---------------------------------------------------------------------------

def extract_entities(text: str, catalog: list) -> dict:
    """
    Generic Unified Entity Extractor.
    Extracts all possible domain entities (product, size_ml, quantity, payment_method, period)
    from user input in a single unified pass, independent of pending slots or current FSM state.
    """
    entities = {
        "product": None,
        "size_ml": None,
        "quantity": None,
        "period": None,
        "payment_method": None
    }

    # 1. Product
    prod = _extract_product_from_catalog(text, catalog)
    if prod:
        entities["product"] = prod

    # 2. Size ML
    size = _extract_size_ml(text)
    if size:
        entities["size_ml"] = size
    elif any(w in text.lower() for w in ["besar", "large", "gede"]):
        entities["size_ml"] = 100
    elif any(w in text.lower() for w in ["kecil", "small", "mini"]):
        entities["size_ml"] = 50

    # 3. Quantity
    qty = _extract_quantity(text)
    if qty is None:
        # Strip out size_ml patterns (e.g. 50ml) so we don't misinterpret "50ml" as qty=50
        clean_text = re.sub(r"\b\d{2,3}\s*ml\b", "", text.lower())
        m = re.search(r"\b(\d+)\s*(pcs?|piece|botol|unit)?\b", clean_text)
        if m:
            val = int(m.group(1))
            if val < 1000:
                qty = val
        if qty is None:
            word_map = {"satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5,
                        "enam": 6, "tujuh": 7, "delapan": 8, "sembilan": 9, "sepuluh": 10}
            for word, num in word_map.items():
                if word in clean_text:
                    qty = num
                    break
    if qty:
        entities["quantity"] = qty

    # 4. Payment Method
    payment = _extract_payment(text)
    if payment:
        entities["payment_method"] = payment.upper()

    # 5. Period
    period_data = _extract_period_with_range(text)
    if period_data:
        entities["period"] = period_data["label"]
        entities["start_date"] = period_data["start_date"]
        entities["end_date"] = period_data["end_date"]

    return entities


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
    # Layer 2.5 — Early non-purchase intent detection (BEFORE pending slot)#
    # If user sends a clearly non-PURCHASE/RESTOCK intent while a pending  #
    # slot is active, clear the slot and handle the new intent properly.   #
    # ------------------------------------------------------------------ #
    early_intent = _detect_non_purchase_intent(input_text)
    if early_intent and pending:
        # User switched topic — clear pending slot and handle new intent
        rule_frame = _semantic_frame_from_rules(input_text, catalog)
        if rule_frame and rule_frame.get("goal") not in ["PURCHASE", "RESTOCK", None]:
            _update_resolved_entities(rule_frame, resolved)
            return {**_wrap(rule_frame), "resolved_entities": resolved, "pending_slot": ""}

    # ------------------------------------------------------------------ #
    # Layer 1 — Pending slot filling (with Generic Entity Extraction)     #
    # Only trigger when pending slot exists AND current goal is still the #
    # same PURCHASE/RESTOCK context.                                      #
    # ------------------------------------------------------------------ #
    if pending:
        slot_frame = _fill_pending_slot(input_text, pending, resolved, conv_ctx, catalog)
        if slot_frame:
            _update_resolved_entities(slot_frame, resolved)
            pending_out = "" if not slot_frame.get("ambiguities") else pending
            return {**_wrap(slot_frame), "resolved_entities": resolved, "pending_slot": pending_out}

    # ------------------------------------------------------------------ #
    # Layer 2 — Deterministic coreference resolver                        #
    # ------------------------------------------------------------------ #
    coref_frame = _deterministic_coreref_resolver(input_text, resolved, conv_ctx, catalog)
    if coref_frame:
        _update_resolved_entities(coref_frame, resolved)
        return {**_wrap(coref_frame), "resolved_entities": resolved}

    # ------------------------------------------------------------------ #
    # Layer 3 — Rule-based extraction (Generic Entity Extractor)          #
    # ------------------------------------------------------------------ #
    rule_frame = _semantic_frame_from_rules(input_text, catalog)
    if rule_frame:
        _update_resolved_entities(rule_frame, resolved)
        return {**_wrap(rule_frame), "resolved_entities": resolved}

    # ------------------------------------------------------------------ #
    # Layer 4 — LLM fallback                                              #
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
# Layer 0 — Active workflow context lock
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
# Layer 1 — Pending slot filling using Generic Entity Extractor
# ---------------------------------------------------------------------------

def _fill_pending_slot(input_text: str, pending: str, resolved: dict, conv_ctx: dict, catalog: list):
    text     = input_text.strip().lower()
    goal     = conv_ctx.get("conversation_goal") or resolved.get("last_goal") or "PURCHASE"

    extracted = extract_entities(input_text, catalog)

    product  = extracted.get("product") or resolved.get("last_product") or conv_ctx.get("current_product")
    size_ml  = extracted.get("size_ml") or resolved.get("last_variant") or conv_ctx.get("current_variant")
    quantity = extracted.get("quantity") or resolved.get("last_quantity") or conv_ctx.get("current_quantity")
    payment  = extracted.get("payment_method") or resolved.get("last_payment")

    if goal in ["PURCHASE", "RESTOCK"]:
        frame = _make_purchase_or_goal_frame(goal, product, size_ml, quantity, catalog)
        if payment:
            frame["entities"]["payment_method"] = payment
        return frame

    if pending == "period" or goal == "REPORT_CHECK":
        period_data = _extract_period_with_range(text)
        if period_data:
            frame = _make_frame("REPORT_CHECK", intent="CHECK_REPORT", ops=["CHECK_REPORT"])
            frame["entities"]["period"]     = period_data["label"]
            frame["entities"]["start_date"] = period_data["start_date"]
            frame["entities"]["end_date"]   = period_data["end_date"]
            return frame

    return None


def _make_purchase_or_goal_frame(goal: str, product, size_ml, quantity, catalog: list):
    ambiguities = []

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
    if goal in ["PURCHASE", "RESTOCK"] and not quantity:
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
            "quantity":       quantity,
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

_COREF_PRODUCT_PATTERNS = [
    r"\byang\s+itu\b", r"\byang\s+tadi\b", r"\bitu\b", r"\btadi\b",
    r"\byang\s+sama\b", r"\bproduk\s+yang\s+sama\b"
]
_SIZE_SHORTCUTS = {
    "besar": 100, "large": 100, "gede": 100,
    "kecil": 50,  "small": 50,  "mini": 30
}


def _deterministic_coreref_resolver(input_text: str, resolved: dict, conv_ctx: dict, catalog: list):
    text    = input_text.strip().lower()
    product = resolved.get("last_product") or conv_ctx.get("current_product")
    size_ml = resolved.get("last_variant")  or conv_ctx.get("current_variant")
    goal    = conv_ctx.get("conversation_goal")

    extracted = extract_entities(input_text, catalog)
    size_only = extracted.get("size_ml")
    has_product_in_text = bool(extracted.get("product"))

    if size_only and not has_product_in_text and product:
        inferred_goal = goal if goal in ["PURCHASE", "PRICE_CHECK", "STOCK_CHECK", "RESTOCK"] else "PRICE_CHECK"
        return _make_purchase_or_goal_frame(inferred_goal, product, size_only, extracted.get("quantity"), catalog)

    has_coref = any(re.search(p, text) for p in _COREF_PRODUCT_PATTERNS)
    if has_coref and product:
        override_size = extracted.get("size_ml") or size_ml
        inferred_goal = goal if goal in ["PURCHASE", "PRICE_CHECK", "STOCK_CHECK", "RESTOCK"] else "PRICE_CHECK"
        return _make_purchase_or_goal_frame(inferred_goal, product, override_size, extracted.get("quantity"), catalog)

    price_q_patterns = [r"\bharganya\b", r"\bberapa harga\b", r"\bharga(?:nya)?\b"]
    if product and any(re.search(p, text) for p in price_q_patterns) and not has_product_in_text:
        override_size = extracted.get("size_ml") or size_ml
        return _make_purchase_or_goal_frame("PRICE_CHECK", product, override_size, None, catalog)

    stock_q_patterns = [r"\bstoknya\b", r"\bstok(?:nya)?\s+ada\b", r"\bada\s+stok\b"]
    if product and any(re.search(p, text) for p in stock_q_patterns) and not has_product_in_text:
        override_size = extracted.get("size_ml") or size_ml
        return _make_purchase_or_goal_frame("STOCK_CHECK", product, override_size, None, catalog)

    buy_patterns = [r"\bbeli\b", r"\border\b", r"\bpesan\b", r"\blanjut\s+beli\b", r"\boke\s+beli\b"]
    if product and any(re.search(p, text) for p in buy_patterns) and not has_product_in_text:
        override_size = extracted.get("size_ml") or size_ml
        qty = extracted.get("quantity")
        ambigs = []
        if not override_size: ambigs.append("size_ml")
        if not qty: ambigs.append("quantity")
        return {
            "goal": "PURCHASE",
            "intent": "BUY_PRODUCT",
            "entities": {
                "product": product, "size_ml": override_size,
                "quantity": qty or 1, "period": None, "payment_method": extracted.get("payment_method")
            },
            "requested_operations": ["CHECK_STOCK"],
            "confidence": 0.95,
            "ambiguities": ambigs
        }

    return None


# ---------------------------------------------------------------------------
# Layer 3 — Rule-based extraction (Generic Entity Extractor)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Pre-detection helper: identify clearly non-PURCHASE/RESTOCK goals
# ---------------------------------------------------------------------------
_NON_PURCHASE_TRIGGERS = [
    "laporan", "report", "rekap", "penjualan", "sales", "omset", "statistik",
    "ringkasan", "berapa terjual", "rekomendasi", "recommend", "suggest", "saran",
    "cocok untuk", "parfum untuk", "parfum pria", "parfum wanita", "parfum unisex",
    "bantuan", "help", "bisa apa", "fitur", "apa saja", "apa aja", "cara pakai",
    "panduan", "tutorial", "katalog", "daftar parfum", "list parfum", "semua parfum",
    "produk apa saja", "koleksi", "terima kasih", "makasih", "thanks", "thank you",
    "reorder", "restock", "restok", "produksi", "tambah stok", "cek stok", "cek harga",
    "halo", "hai", "selamat", "hi", "hei", "assalamualaikum"
]

def _detect_non_purchase_intent(input_text: str) -> bool:
    """Return True if input clearly signals a non-PURCHASE/RESTOCK domain intent."""
    text = input_text.lower()
    return any(t in text for t in _NON_PURCHASE_TRIGGERS)


def _semantic_frame_from_rules(input_text: str, catalog: list):
    text = input_text.lower()
    goal = None

    # ── High-specificity patterns checked FIRST ──────────────────────────
    if any(w in text for w in ["apakah otomatis", "apakah sistem otomatis", "apakah po otomatis", "otomatis reorder", "otomatis po", "otomatis buat po"]):
        goal = "FAQ_FEATURE"
    elif any(w in text for w in ["nilai inventori", "nilai stok", "total nilai inventori"]):
        goal = "INVENTORY_VALUE_CHECK"
    elif any(w in text for w in ["status po", "purchase order", "po berjalan"]):
        goal = "PO_CHECK"
    elif any(w in text for w in ["bahan baku", "formula", "komposisi", "piramida notes", "top note", "heart note", "base note"]):
        goal = "FORMULA_CHECK"
    elif any(w in text for w in ["supplier", "pemasok"]):
        goal = "SUPPLIER_CHECK"
    elif any(w in text for w in ["stok di bawah", "hampir habis", "stok menipis", "stok <", "kurang dari 5", "di bawah 5"]):
        goal = "LOW_STOCK_CHECK"
    elif any(w in text for w in ["reorder", "restock", "restok", "produksi", "tambah stok",
                                "buat stok", "order stok", "pesan stok", "stock masuk",
                                "stok baru", "supply", "pengiriman", "stock in", "masuk barang"]):
        goal = "RESTOCK"
    elif any(w in text for w in ["cek harga", "berapa harga", "harga berapa",
                                  "seberapa mahal", "harga barang", "bandingkan harga",
                                  "harganya", "perbedaan harga"]):
        goal = "PRICE_CHECK"
    elif any(w in text for w in ["cek stok", "stok ada", "ada stok", "stok berapa",
                                  "berapa stok", "ketersediaan", "ready", "tersedia",
                                  "masih ada", "ada gak"]):
        goal = "STOCK_CHECK"
    elif any(w in text for w in ["laporan", "report", "rekap", "penjualan", "sales",
                                  "omset", "pendapatan", "statistik", "ringkasan", "berapa terjual",
                                  "top 3", "terlaris", "produk terlaris", "bulan ini vs"]):
        goal = "REPORT_CHECK"
    elif any(w in text for w in ["unisex", "produk unisex", "parfum unisex", "rekomendasi", "recommend", "suggest", "saran",
                                  "cocok untuk", "parfum untuk", "parfum pria",
                                  "parfum wanita", "terjangkau",
                                  "harga yang terjangkau", "yang murah", "paling murah",
                                  "woody", "floral", "citrus", "oriental", "fresh"]):
        goal = "RECOMMENDATION"
    elif any(w in text for w in ["bantuan", "help", "bisa apa", "fitur", "apa saja",
                                  "apa aja", "cara pakai", "panduan", "tutorial"]):
        goal = "HELP"
    elif any(w in text for w in ["terima kasih", "makasih", "thanks", "thank you", "tq", "thx", "trims"]):
        goal = "GRATITUDE"
    elif any(w in text for w in ["katalog", "daftar parfum", "list parfum", "semua parfum",
                                  "produk apa saja", "koleksi"]):
        goal = "CATALOG_CHECK"
    elif any(w in text for w in ["halo", "hai", "selamat", "hi", "hei",
                                  "assalamualaikum", "pagi", "siang", "sore", "malam"]):
        goal = "GREETING"
    elif any(w in text for w in ["tunai", "cash", "transfer", "bca", "qris", "gopay",
                                  "ovo", "mandiri", "shopeepay", "linkaja", "bri",
                                  "rekening", "cicilan"]):
        goal = "PAYMENT_METHOD"
    elif any(w in text for w in ["tidak", "batal", "ga jadi", "cancel", "nggak",
                                  "gak mau", "jangan", "enggak", "tidak jadi", "skip", "lewat"]):
        goal = "REJECT"
    # CONFIRM only matches short standalone affirmative responses (<=4 words)
    # Use regex word boundaries to avoid "ya" matching "saya", "ayo" matching "kayo", etc.
    elif len(text.split()) <= 4 and re.search(
        r'\b(iya|ya|ok|oke|lanjut|gas|sip|betul|benar|setuju|yes|ayo)\b', text
    ):
        goal = "CONFIRM"
    # ── PURCHASE checked LAST and only with explicit purchase-action keywords ──
    elif any(w in text for w in ["mau beli", "ingin beli", "beli dong", "beli aja",
                                  "checkout", "transaksi", "beli sekarang"]):
        goal = "PURCHASE"
    elif any(w in text for w in ["saya mau", "saya ingin", "aku mau", "aku ingin"]) and \
         any(w in text for w in ["beli", "pesan", "order", "ambil"]):
        # "saya ingin beli", "saya mau pesan" → PURCHASE even without catalog product
        goal = "PURCHASE"
    elif any(w in text for w in ["beli", "pesan", "order", "ambil"]) and \
         _extract_product_from_catalog(input_text, catalog):
        # Only PURCHASE if there's actually a product in the catalog mentioned
        goal = "PURCHASE"
    elif any(w in text for w in ["saya mau", "saya ingin", "aku mau", "aku ingin"]) and \
         _extract_product_from_catalog(input_text, catalog):
        # "saya mau/ingin [product name]" → PURCHASE only when catalog product present
        goal = "PURCHASE"

    # Out-of-domain / tidak relevan dengan toko parfum
    # Jika kalimat mengandung "saya mau/ingin" tapi tidak ada produk & tidak ada purchase keyword
    _purchase_action_words = ["beli", "pesan", "order", "ambil", "checkout", "transaksi"]
    if not goal and any(w in text for w in ["saya mau", "saya ingin", "aku mau", "aku ingin"]) and \
       not any(w in text for w in _purchase_action_words) and \
       not _extract_product_from_catalog(input_text, catalog):
        # Out-of-domain: "saya mau tidur", "saya mau makan", dll
        return {
            "goal": "UNKNOWN",
            "intent": "OUT_OF_DOMAIN",
            "entities": {"product": None, "size_ml": None, "quantity": None, "period": None, "payment_method": None},
            "requested_operations": [],
            "confidence": 0.9,
            "ambiguities": []
        }

    if not goal:
        return None

    extracted = extract_entities(input_text, catalog)
    product   = extracted.get("product")
    size_ml   = extracted.get("size_ml")
    quantity  = extracted.get("quantity")
    payment   = extracted.get("payment_method")
    period_data = _extract_period_with_range(text)
    ambiguities = []

    if goal in ["PURCHASE", "RESTOCK"]:
        if not product:     ambiguities.append("product")
        if not size_ml:     ambiguities.append("size_ml")
        if not quantity:    ambiguities.append("quantity")
    if goal == "REPORT_CHECK" and not period_data:
        ambiguities.append("period")

    entities = {
        "product":        product,
        "size_ml":        size_ml,
        "quantity":       quantity,
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
| RECOMMENDATION | []                                                      |
| HELP           | []                                                      |
| UNKNOWN        | []                                                      |

ATURAN PENTING:
- CONFIRM HANYA untuk kalimat pendek (<=4 kata) yang benar-benar bermakna setuju/konfirmasi: "ok", "iya", "lanjut", "setuju", "yes".
- Kalimat seperti "saya mau tidur", "saya mau makan", "saya capek" adalah UNKNOWN (bukan domain parfum).
- Kalimat "saya ingin beli" tanpa produk = PURCHASE dengan ambiguities=["product", "size_ml", "quantity"].
- Kalimat "tolong", "bantu" tanpa konteks = HELP atau UNKNOWN, BUKAN PURCHASE.
- Jangan paksa setiap kalimat menjadi PURCHASE atau CONFIRM.

EKSTRAKSI ENTITAS SIMULTAN:
Ekstrak SELURUH entitas yang ada di teks user tanpa terbatas pada slot yang sedang ditunggu.
- size_ml: integer (30, 50, 100)
- quantity: integer (jumlah botol)
- payment_method: "tunai", "transfer", "qris", "gopay", "ovo"

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

        ambiguities = semantic_frame.setdefault("ambiguities", [])
        entities    = semantic_frame.setdefault("entities", {})
        goal        = semantic_frame.get("goal", "UNKNOWN")

        _apply_context_lock(input_text, semantic_frame, conv_ctx, tx_ctx)
        entities = semantic_frame.setdefault("entities", {})
        goal     = semantic_frame.get("goal", "UNKNOWN")

        # Merge generic extracted entities
        extracted = extract_entities(input_text, catalog)
        for k, v in extracted.items():
            if v and not entities.get(k):
                entities[k] = v

        product = entities.get("product")
        if product:
            matched = _match_product_to_catalog(product, catalog)
            if matched:
                entities["product"] = matched
            else:
                entities["product"] = "UNKNOWN_PRODUCT"
                if "product" not in ambiguities:
                    ambiguities.append("product")

        if goal in ["PURCHASE", "RESTOCK"] and (not entities.get("product") or entities.get("product") == "UNKNOWN_PRODUCT"):
            if "product" not in ambiguities:
                ambiguities.append("product")
        if goal in ["PURCHASE", "RESTOCK"] and not entities.get("size_ml"):
            if "size_ml" not in ambiguities:
                ambiguities.append("size_ml")
        if goal in ["PURCHASE", "RESTOCK"] and not entities.get("quantity"):
            if "quantity" not in ambiguities:
                ambiguities.append("quantity")
        if goal == "REPORT_CHECK" and not entities.get("period"):
            if "period" not in ambiguities:
                ambiguities.append("period")

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

_KNOWN_BRANDS = ["ysl", "jo malone", "tom ford", "le labo", "hermes", "hermès", "dior", "chanel", "gucci", "byredo", "burberry"]

def _extract_product_from_catalog(text: str, catalog: list):
    text_lower = text.lower()
    compact = re.sub(r"[^a-z0-9]+", " ", text_lower).strip()

    # Detect if any brand name is explicitly present in user text
    detected_brand = None
    for brand in _KNOWN_BRANDS:
        if re.search(r'\b' + re.escape(brand) + r'\b', compact):
            detected_brand = brand
            break

    # If brand detected, filter catalog candidates to those matching the brand
    candidates = catalog
    if detected_brand:
        brand_matches = [p for p in catalog if detected_brand in p.lower()]
        if brand_matches:
            candidates = brand_matches

    # 1. Substring match on candidate products
    for product in candidates:
        if product.lower() in text_lower:
            return product

    # 2. Token overlap fallback
    text_tokens = set(compact.split())
    best_match, best_score = None, 0
    for product in candidates:
        product_tokens = set(re.sub(r"[^a-z0-9]+", " ", product.lower()).split())
        score = len(product_tokens & text_tokens)
        if score > best_score:
            best_match, best_score = product, score

    return best_match if best_score >= 1 else (candidates[0] if (detected_brand and candidates) else None)


def _match_product_to_catalog(product: str, catalog: list):
    for p in catalog:
        if p.lower() in product.lower() or product.lower() in p.lower():
            return p
    return None


def _extract_size_ml(text: str):
    match = re.search(r"\b(\d{2,3})\s*ml\b", text.lower())
    return int(match.group(1)) if match else None


def _extract_quantity(text: str):
    match = re.search(r"\b(\d+)\s*(pcs?|piece|botol|unit)\b", text.lower())
    return int(match.group(1)) if match else None


def _extract_payment(text: str):
    for method in ["tunai", "cash", "transfer", "bca", "qris", "gopay", "ovo", "mandiri"]:
        if method in text.lower():
            return method
    return None


def _extract_period_with_range(text: str) -> dict | None:
    today = datetime.now().date()
    
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
                today = max_date
    except Exception:
        pass

    def iso(d):
        return d.strftime("%Y-%m-%d")

    mappings = [
        (["hari ini", "today"], "hari ini", today, today),
        (["kemarin", "yesterday"], "kemarin", today - timedelta(days=1), today - timedelta(days=1)),
        (["lusa"], "lusa", today - timedelta(days=2), today - timedelta(days=2)),
        (["minggu ini", "this week"], "minggu ini", today - timedelta(days=today.weekday()), today - timedelta(days=today.weekday()) + timedelta(days=6)),
        (["minggu lalu", "pekan lalu", "last week"], "minggu lalu", today - timedelta(days=today.weekday() + 7), today - timedelta(days=today.weekday() + 1)),
        (["bulan ini", "this month"], "bulan ini", today.replace(day=1), today),
        (["bulan lalu", "last month"], "bulan lalu", (today.replace(day=1) - timedelta(days=1)).replace(day=1), today.replace(day=1) - timedelta(days=1)),
        (["awal bulan"], "awal bulan", today.replace(day=1), today.replace(day=10)),
        (["akhir bulan"], "akhir bulan", today.replace(day=21), today),
        (["triwulan lalu", "q1", "q2", "q3", "q4", "kuartal lalu"], "triwulan lalu", None, None),
        (["semester lalu", "semester ini"], "semester lalu", None, None),
        (["tahun ini", "this year"], "tahun ini", today.replace(month=1, day=1), today),
        (["tahun lalu", "last year"], "tahun lalu", today.replace(year=today.year - 1, month=1, day=1), today.replace(year=today.year - 1, month=12, day=31)),
    ]

    for keywords, label, start, end in mappings:
        if any(kw in text.lower() for kw in keywords):
            return {
                "label":      label,
                "start_date": iso(start) if start else None,
                "end_date":   iso(end)   if end   else None
            }
    return None


def _build_history_prompt(history: list, limit: int = CONTEXT_WINDOW) -> str:
    if not history:
        return ""

    recent = list(history)[-limit:]
    lines  = ["Conversation History:"]
    for msg in recent:
        role    = msg.get("role", "user").upper()
        content = msg.get("content", "").strip()
        lines.append(f"\n{role}:\n{content}")

    return "\n".join(lines)


def _update_resolved_entities(frame: dict, resolved: dict):
    entities = frame.get("entities", {})
    if entities.get("product") and entities["product"] != "UNKNOWN_PRODUCT":
        resolved["last_product"] = entities["product"]
    if entities.get("size_ml"):
        resolved["last_variant"] = entities["size_ml"]
    if entities.get("quantity"):
        resolved["last_quantity"] = entities["quantity"]
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
