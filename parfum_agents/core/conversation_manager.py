import time
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from models import AgentState

SYSTEM_COMMANDS = {
    "reset": "RESET",
    "/reset": "RESET",
    "batal": "CANCEL",
    "cancel": "CANCEL",
    "/cancel": "CANCEL",
    "help": "HELP",
    "/help": "HELP",
    "bantuan": "HELP",
    "menu": "MENU",
    "/menu": "MENU",
    "exit": "EXIT",
    "/exit": "EXIT"
}

def handle_system_command(user_input: str, state: AgentState) -> dict | None:
    start_time = time.time()
    text = user_input.strip().lower()
    
    command = SYSTEM_COMMANDS.get(text)
    if not command:
        return None
        
    latency = (time.time() - start_time) * 1000
    
    if command == "RESET":
        return {
            "system_command_triggered": True,
            "system_command": "RESET",
            "final_response": "[RESET] Sesi transaksi & ingatan percakapan telah dibersihkan. Preferensi Anda tetap tersimpan. Ada yang bisa saya bantu kembali?",
            "_metrics": {
                "agent": "ConversationManager",
                "latency_ms": latency,
                "decision": "SYSTEM_RESET",
                "status": "OK"
            }
        }
        
    elif command == "CANCEL":
        return {
            "system_command_triggered": True,
            "system_command": "CANCEL",
            "workflow_state": "CANCELLED",
            "final_response": "[CANCEL] Transaksi berhasil dibatalkan. Ada lagi yang bisa saya bantu?",
            "_metrics": {
                "agent": "ConversationManager",
                "latency_ms": latency,
                "decision": "SYSTEM_CANCEL",
                "status": "OK"
            }
        }
        
    elif command in ["HELP", "MENU"]:
        menu_text = (
            "Berikut hal-hal yang bisa saya bantu:\n\n"
            "🛒 **Pembelian** — \"Beli Chanel Noir 50ml\"\n"
            "💰 **Cek Harga** — \"Berapa harga YSL Ratione Noir?\"\n"
            "📦 **Cek Stok** — \"Stok Tom Ford Intense ada?\"\n"
            "📊 **Laporan Penjualan** — \"Laporan bulan ini\"\n"
            "🔄 **Restock/Reorder** — \"Restok Tom Ford Intense 50ml 50 botol\"\n"
            "🎯 **Rekomendasi** — \"Rekomendasi parfum untuk pria\"\n\n"
            "Silakan ketik pertanyaan Anda!"
        )
        return {
            "system_command_triggered": True,
            "system_command": command,
            "final_response": menu_text,
            "_metrics": {
                "agent": "ConversationManager",
                "latency_ms": latency,
                "decision": "SYSTEM_HELP",
                "status": "OK"
            }
        }
        
    elif command == "EXIT":
        return {
            "system_command_triggered": True,
            "system_command": "EXIT",
            "final_response": "Terima kasih telah menggunakan Parfum Enterprise Assistant. Sampai jumpa!",
            "_metrics": {
                "agent": "ConversationManager",
                "latency_ms": latency,
                "decision": "SYSTEM_EXIT",
                "status": "OK"
            }
        }
        
    return None
