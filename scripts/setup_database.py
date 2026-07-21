import os
import sys
import sqlite3
import glob

# Ensure config can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

def apply_migrations():
    migrations_dir = os.path.join(os.path.dirname(config.DB_PATH), "migrations")
    
    if not os.path.exists(migrations_dir):
        print(f"Directory not found: {migrations_dir}")
        return

    # Cari file SQL berurutan
    sql_files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))
    
    if not sql_files:
        print("No migration files found.")
        return
        
    conn = sqlite3.connect(config.DB_PATH)
    c = conn.cursor()
    
    try:
        # Create a table to track applied migrations
        c.execute('''
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
        ''')
        
        # Get applied migrations
        c.execute("SELECT version FROM schema_migrations")
        applied = {row[0] for row in c.fetchall()}
        
        for sql_file in sql_files:
            filename = os.path.basename(sql_file)
            if filename in applied:
                print(f"Skipping {filename} (already applied)")
                continue
                
            print(f"Applying migration: {filename}...")
            with open(sql_file, 'r', encoding='utf-8') as f:
                sql_script = f.read()
                
            try:
                # Use executescript to run multiple statements at once
                c.executescript(sql_script)
                
                # Record migration
                import datetime
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                c.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", (filename, now))
                conn.commit()
                print(f"Successfully applied {filename}")
                
            except Exception as e:
                conn.rollback()
                print(f"Error applying {filename}: {e}")
                print("Migration aborted.")
                break
                
    finally:
        conn.close()

if __name__ == "__main__":
    apply_migrations()
