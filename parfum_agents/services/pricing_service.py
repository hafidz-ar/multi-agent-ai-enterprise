import os
import sys
import time
import uuid

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config
from models import AgentState, AgentResult, Action
from parfum_agents.core.base_agent import BaseSpecialistAgent
from parfum_agents.repositories import CatalogRepository

class PricingAgent(BaseSpecialistAgent):
    """Specialist Agent performing Business Enrichment & Price Calculations."""

    def __init__(self, catalog_repo: CatalogRepository = None):
        self.catalog_repo = catalog_repo or CatalogRepository()

    def execute(self, state: AgentState) -> AgentResult:
        start_time = time.time()
        exec_id = str(uuid.uuid4())
        
        semantic_frame = state.get("semantic_frame", {})
        entities = semantic_frame.get("entities", {})
        context = state.get("conversation_context", {})
        resolved = state.get("resolved_entities", {})
        tx_context = state.get("transaction_context", {})
        
        product_name = entities.get("product") or tx_context.get("product") or context.get("current_product") or resolved.get("last_product")
        requested_size = entities.get("size_ml") or tx_context.get("size_ml") or context.get("current_variant") or resolved.get("last_variant")
        qty = entities.get("quantity") or tx_context.get("qty") or 1

        if not product_name or product_name == "UNKNOWN_PRODUCT":
            latency = (time.time() - start_time) * 1000
            return AgentResult(
                execution_id=exec_id,
                action=Action.CHECK_PRICE,
                service_name="PricingAgent",
                success=False,
                data={},
                errors=("Missing product_name in semantic_frame and context",),
                user_message="Mohon maaf, saya belum menangkap produk apa yang ingin Anda cek harganya.",
                latency_ms=latency
            )

        prod = self.catalog_repo.find_product_by_name(product_name)
        if not prod:
            latency = (time.time() - start_time) * 1000
            return AgentResult(
                execution_id=exec_id,
                action=Action.CHECK_PRICE,
                service_name="PricingAgent",
                success=False,
                data={},
                errors=(f"Product '{product_name}' not found in perfume_catalog",),
                user_message=f"Mohon maaf, produk {product_name} tidak ditemukan dalam katalog kami.",
                latency_ms=latency
            )

        perfume_id, actual_name, category, price = prod
        rows = self.catalog_repo.get_variant_prices(perfume_id)
        
        prices = {}
        for r in rows:
            size = r[0]
            base_price = r[1]
            if size == 100:
                calc_price = base_price
            elif size == 50:
                calc_price = int(base_price * 0.65)
            elif size == 30:
                calc_price = int(base_price * 0.45)
            else:
                calc_price = int(base_price * (size / 100.0))
            prices[f"{size}ml"] = calc_price
            
        unit_price = prices.get(f"{requested_size}ml", 0) if requested_size else (prices.get("100ml", 0) or prices.get("50ml", 0))
        total_price = unit_price * qty
        latency = (time.time() - start_time) * 1000

        data = {
            "product": actual_name,
            "size_ml": requested_size,
            "qty": qty,
            "unit_price": unit_price,
            "total_price": total_price,
            "prices": prices
        }

        return AgentResult(
            execution_id=exec_id,
            action=Action.CHECK_PRICE,
            service_name="PricingAgent",
            success=True,
            data=data,
            user_message=f"Harga untuk {actual_name} berhasil ditemukan.",
            latency_ms=latency
        )

# Backward-compatible wrapper function
def run(state: AgentState) -> dict:
    agent = PricingAgent()
    result = agent.execute(state)
    return {
        "services_results": [result.to_dict()],
        "_metrics": {
            "agent": "PricingService",
            "latency_ms": result.latency_ms,
            "decision": "PRICE_FETCHED" if result.success else "PRICE_ERROR",
            "status": "OK" if result.success else "ERROR",
            "execution_id": result.execution_id
        }
    }
