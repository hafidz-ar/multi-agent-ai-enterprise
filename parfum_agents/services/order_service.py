import os
import sys
import time
import uuid
import sqlite3
import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config
from models import AgentState, AgentResult, Action
from parfum_agents.core.base_agent import BaseSpecialistAgent
from parfum_agents.repositories import CatalogRepository, InventoryRepository, OrderRepository

class OrderAgent(BaseSpecialistAgent):
    """Atomic Transaction Orchestrator executing stock deduction & sales history persistence."""

    def __init__(
        self,
        catalog_repo: CatalogRepository = None,
        inventory_repo: InventoryRepository = None,
        order_repo: OrderRepository = None,
        db_path: str = None
    ):
        self.db_path = db_path or config.DB_PATH
        self.catalog_repo = catalog_repo or CatalogRepository(self.db_path)
        self.inventory_repo = inventory_repo or InventoryRepository(self.db_path)
        self.order_repo = order_repo or OrderRepository(self.db_path)

    def execute(self, state: AgentState) -> AgentResult:
        start_time = time.time()
        exec_id = str(uuid.uuid4())
        
        tx_context = state.get("transaction_context", {})
        semantic_frame = state.get("semantic_frame", {})
        entities = semantic_frame.get("entities", {})
        context = state.get("conversation_context", {})
        resolved = state.get("resolved_entities", {})

        payment_method = tx_context.get("payment_method") or entities.get("payment_method") or resolved.get("last_payment")

        if not payment_method:
            return self._error_result(exec_id, start_time, "Metode pembayaran belum dipilih.")

        product_name = (
            tx_context.get("product") or 
            entities.get("product") or 
            context.get("current_product") or 
            resolved.get("last_product")
        )
        size_ml = (
            tx_context.get("size_ml") or 
            entities.get("size_ml") or 
            context.get("current_variant") or 
            resolved.get("last_variant") or 50
        )
        qty = (
            tx_context.get("qty") or 
            entities.get("quantity") or 
            context.get("current_quantity") or 1
        )

        prod = self.catalog_repo.find_product_by_name(product_name) if product_name else None
        if not prod:
            return self._error_result(exec_id, start_time, f"Produk '{product_name}' tidak ditemukan di katalog.")

        perfume_id, p_name, category, price = prod

        if size_ml == 100:
            unit_price = price
        elif size_ml == 50:
            unit_price = int(price * 0.65)
        elif size_ml == 30:
            unit_price = int(price * 0.45)
        else:
            unit_price = int(price * (size_ml / 100.0))

        total_price = unit_price * qty
        invoice_no = f"INV-{datetime.datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4().hex[:4]).upper()}"
        tx_id = tx_context.get("transaction_id", invoice_no)

        # Atomic Transaction Block
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("BEGIN TRANSACTION")

            # 1. Atomic Stock Update
            success_update = self.inventory_repo.update_stock_atomic(conn, perfume_id, size_ml, qty)
            if not success_update:
                conn.rollback()
                current_stock = self.inventory_repo.get_available_quantity(perfume_id, size_ml)
                return self._error_result(
                    exec_id, start_time,
                    f"Stok {p_name} {size_ml}ml tidak mencukupi (tersisa {current_stock} pcs, diminta {qty} pcs)."
                )

            # 2. Atomic Sales History Insert
            self.order_repo.insert_sales_history_atomic(
                conn, tx_id, perfume_id, p_name, category,
                size_ml, qty, unit_price, total_price
            )

            # Commit Transaction
            conn.commit()

        except Exception as e:
            if conn:
                conn.rollback()
            return self._error_result(exec_id, start_time, f"Database Transaction Error: {str(e)}")
        finally:
            if conn:
                conn.close()

        # Read remaining stock post-commit
        remaining_stock = self.inventory_repo.get_available_quantity(perfume_id, size_ml)
        latency = (time.time() - start_time) * 1000

        data = {
            "invoice": invoice_no,
            "transaction_id": tx_id,
            "product": p_name,
            "size_ml": size_ml,
            "qty": qty,
            "unit_price": unit_price,
            "subtotal": total_price,
            "total_price": total_price,
            "payment_method": payment_method,
            "remaining_stock": remaining_stock,
            "status": "COMPLETED"
        }

        user_msg = f"Pesanan Anda untuk {p_name} ({size_ml}ml) sebanyak {qty} botol telah berhasil dibuat dengan nomor transaksi {invoice_no}."

        return AgentResult(
            execution_id=exec_id,
            action=Action.CREATE_ORDER,
            service_name="OrderAgent",
            success=True,
            data=data,
            user_message=user_msg,
            latency_ms=latency
        )

    def _error_result(self, exec_id: str, start_time: float, msg: str) -> AgentResult:
        latency = (time.time() - start_time) * 1000
        return AgentResult(
            execution_id=exec_id,
            action=Action.CREATE_ORDER,
            service_name="OrderAgent",
            success=False,
            data={},
            errors=(msg,),
            user_message=f"Mohon maaf, pesanan gagal diproses: {msg}",
            latency_ms=latency
        )

# Backward-compatible wrapper function
def run(state: AgentState) -> dict:
    agent = OrderAgent()
    result = agent.execute(state)
    res_dict = result.to_dict()

    tx_context = state.get("transaction_context", {}).copy()
    if result.success:
        tx_context["status"] = "COMPLETED"
        tx_context["invoice_no"] = result.data.get("invoice")
        tx_context["unit_price"] = result.data.get("unit_price")
        tx_context["subtotal"] = result.data.get("subtotal")
        tx_context["remaining_stock"] = result.data.get("remaining_stock")
        tx_context["product"] = result.data.get("product")
        tx_context["size_ml"] = result.data.get("size_ml")
        tx_context["qty"] = result.data.get("qty")
        tx_context["payment_method"] = result.data.get("payment_method")
    else:
        tx_context["status"] = "FAILED"

    return {
        "services_results": [res_dict],
        "transaction_context": tx_context,
        "workflow_state": "COMPLETED" if result.success else "FAILED",
        "_metrics": {
            "agent": "OrderAgent",
            "latency_ms": result.latency_ms,
            "decision": "ORDER_CREATED" if result.success else "ORDER_FAILED",
            "status": "OK" if result.success else "ERROR",
            "execution_id": result.execution_id
        }
    }
