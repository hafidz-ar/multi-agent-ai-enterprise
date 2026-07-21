import os
import sqlite3
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'raw')
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'database')
DB_PATH = os.path.join(DB_DIR, 'parfum_enterprise.db')

def load_data():
    os.makedirs(DB_DIR, exist_ok=True)
    
    # Connect to SQLite
    print(f"Connecting to SQLite Database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    
    # Files to load
    files = {
        'ingredients': 'ingredients.csv',
        'supplier': 'supplier.csv',
        'perfume_catalog': 'perfume_catalog.csv',
        'inventory': 'inventory.csv',
        'formula': 'formula.csv',
        'sales_history': 'sales_history.csv'
    }
    
    for table_name, filename in files.items():
        file_path = os.path.join(DATA_DIR, filename)
        if os.path.exists(file_path):
            print(f"Loading {filename} into table '{table_name}'...")
            df = pd.read_csv(file_path)
            # Write the data to a sqlite table
            df.to_sql(table_name, conn, if_exists='replace', index=False)
            print(f"Successfully loaded {len(df)} rows into '{table_name}'.")
        else:
            print(f"Warning: {filename} not found in {DATA_DIR}")
            
    conn.close()
    print("Database loading completed.")

if __name__ == '__main__':
    load_data()
