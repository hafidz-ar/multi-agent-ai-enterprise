import os
import sys
import logging
import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config

def setup_logger():
    logger = logging.getLogger("evaluation_logger")
    logger.setLevel(logging.INFO)
    
    # Prevent duplicate handlers
    if not logger.handlers:
        file_handler = logging.FileHandler(config.LOG_PATH, encoding='utf-8')
        formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
    return logger

logger = setup_logger()

def log_evaluation(agent_name: str, input_text: str, output_text: str, duration_sec: float, status: str = "SUCCESS", tokens_used: int = 0, exec_id: str = "N/A"):
    """
    Mencatat eksekusi agent untuk keperluan evaluasi
    """
    # Hanya catat jika DEVELOPER_MODE aktif
    if not getattr(config, "DEVELOPER_MODE", True):
        return
        
    safe_input = str(input_text).replace('\n', ' ').replace('\r', '')
    safe_output = str(output_text).replace('\n', ' ').replace('\r', '')
    
    log_msg = f"AGENT={agent_name} | EXEC_ID={exec_id} | INPUT=\"{safe_input}\" | OUTPUT=\"{safe_output}\" | DURATION={duration_sec:.2f}s | TOKENS_USED={tokens_used} | STATUS={status}"
    logger.info(log_msg)

import random
def generate_transaction_id() -> str:
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    random_str = f"{random.randint(0, 99999):05d}"
    return f"TX-{date_str}-{random_str}"

