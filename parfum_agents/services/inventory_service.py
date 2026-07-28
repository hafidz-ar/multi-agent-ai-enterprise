import os
import sys
import time
import uuid

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config
from models import AgentState, AgentResult, Action
from parfum_agents.core.base_agent import BaseSpecialistAgent
from parfum_agents.repositories import CatalogRepository, InventoryRepository

class InventoryAgent(BaseSpecialistAgent):
    """Specialist Agent performing Read-Only Inventory Stock Checks & Validation."""

    def __init__(self, catalog_repo: CatalogRepository = None, inventory_repo: InventoryRepository = None):
        self.catalog_repo = catalog_repo or CatalogRepository()
        self.inventory_repo = inventory_repo or InventoryRepository()

    def execute(self, state: AgentState) -> AgentResult:
        start_time = time.time()
        exec_id = str(uuid.uuid4())
        
        semantic_frame = state.get("semantic_frame", {})
        entities = semantic_frame.get("entities", {})
        context = state.get("conversation_context", {})
        resolved = state.get("resolved_entities", {})
        tx_context = state.get("transaction_context", {})
        
        product_name = entities.get("product") or tx_context.get("product") or context.get("current_product") or resolved.get("last_product")
        requested_size = entities.get("size_ml") or tx_context.get("size_ml") or context.get("current_variant") or resolved.get("last_variant") or 50
        qty_requested = entities.get("quantity") or tx_context.get("qty") or 1

        if not product_name or product_name == "UNKNOWN_PRODUCT":
            latency = (time.time() - start_time) * 1000
            return AgentResult(
                execution_id=exec_id,
                action=Action.CHECK_STOCK,
                service_name="InventoryAgent",
                success=False,
                data={},
                errors=("Missing product_name in semantic_frame and context",),
                user_message="Mohon maaf, saya belum menangkap produk apa yang ingin Anda cek stoknya.",
                latency_ms=latency
            )

        prod = self.catalog_repo.find_product_by_name(product_name)
        if not prod:
            latency = (time.time() - start_time) * 1000
            return AgentResult(
                execution_id=exec_id,
                action=Action.CHECK_STOCK,
                service_name="InventoryAgent",
                success=False,
                data={},
                errors=(f"Product '{product_name}' not found in perfume_catalog",),
                user_message=f"Mohon maaf, produk {product_name} tidak ditemukan dalam katalog kami.",
                latency_ms=latency
            )

        perfume_id, actual_name, category, price = prod
        rows = self.inventory_repo.get_stock_by_perfume_id(perfume_id)
        
        stock_sizes = {}
        total_available = 0
        status = "HEALTHY"
        need_production = False
        
        for r in rows:
            size_ml, qty_avail, reorder_pt, warehouse = r
            stock_sizes[f"stock_{size_ml}ml"] = qty_avail
            if size_ml == requested_size:
                total_available = qty_avail
                if qty_avail == 0:
                    status = "OUT_OF_STOCK"
                    need_production = True
                elif qty_avail <= reorder_pt:
                    status = "LOW_STOCK"
                    need_production = True
                    
        can_fulfill = total_available >= qty_requested
        remaining_after_order = max(0, total_available - qty_requested)
        variant_details = ", ".join([f"{k.replace('stock_', '')}: {v} pcs" for k, v in stock_sizes.items()])
        latency = (time.time() - start_time) * 1000

        data = {
            "product": actual_name,
            "size_ml": requested_size,
            "stock": total_available,
            "requested_qty": qty_requested,
            "available": can_fulfill,
            "remaining_after_order": remaining_after_order,
            "need_production": need_production,
            "stock_sizes": stock_sizes,
            "status": status
        }

        user_msg = f"Stok {actual_name} {'tersedia' if can_fulfill else 'menipis/habis'} ({variant_details} - Total: {total_available} pcs)."

        return AgentResult(
            execution_id=exec_id,
            action=Action.CHECK_STOCK,
            service_name="InventoryAgent",
            success=can_fulfill,
            data=data,
            user_message=user_msg,
            latency_ms=latency
        )

# Backward-compatible wrapper function
def run(state: AgentState) -> dict:
    agent = InventoryAgent()
    result = agent.execute(state)
    res_dict = result.to_dict()
    
    tx_context = state.get("transaction_context", {}).copy()
    if result.data.get("available"):
        tx_context["status"] = "WAITING_CONFIRMATION"

    return {
        "services_results": [res_dict],
        "transaction_context": tx_context,
        "_metrics": {
            "agent": "InventoryService",
            "latency_ms": result.latency_ms,
            "decision": "STOCK_CHECKED",
            "status": "OK" if result.success else "WARNING",
            "execution_id": result.execution_id
        }
    }
