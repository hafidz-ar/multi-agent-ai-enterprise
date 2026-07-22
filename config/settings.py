import os

# FSM Configuration
WORKFLOW_TIMEOUT = int(os.getenv("WORKFLOW_TIMEOUT", 900))  # 15 minutes

# Feature Flags
DEVELOPER_MODE = True
