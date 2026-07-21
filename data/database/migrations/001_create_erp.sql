-- 1. Production Orders
CREATE TABLE IF NOT EXISTS production_orders (
    id TEXT PRIMARY KEY,
    production_no TEXT NOT NULL UNIQUE,
    perfume_id TEXT NOT NULL,
    variant_id TEXT,
    qty_requested INTEGER NOT NULL,
    qty_produced INTEGER,
    status TEXT CHECK(status IN ('DRAFT', 'READY', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'CANCELLED')),
    formula_version TEXT,
    request_source TEXT,
    created_by TEXT,
    completed_by TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(perfume_id) REFERENCES perfume_catalog(perfume_id)
);

CREATE INDEX IF NOT EXISTS idx_prod_order_status ON production_orders(status);
CREATE INDEX IF NOT EXISTS idx_prod_order_created_at ON production_orders(created_at);

-- 2. Production Order Items
CREATE TABLE IF NOT EXISTS production_order_items (
    id TEXT PRIMARY KEY,
    production_order_id TEXT NOT NULL,
    ingredient_id TEXT NOT NULL,
    required_qty REAL NOT NULL,
    used_qty REAL,
    unit TEXT,
    FOREIGN KEY(production_order_id) REFERENCES production_orders(id),
    FOREIGN KEY(ingredient_id) REFERENCES ingredients(ingredient_id)
);

CREATE INDEX IF NOT EXISTS idx_prod_item_order_id ON production_order_items(production_order_id);

-- 3. Purchase Orders
CREATE TABLE IF NOT EXISTS purchase_orders (
    id TEXT PRIMARY KEY,
    po_number TEXT NOT NULL UNIQUE,
    supplier_id TEXT NOT NULL,
    status TEXT CHECK(status IN ('DRAFT', 'PENDING', 'APPROVED', 'ORDERED', 'RECEIVED', 'CANCELLED')),
    expected_arrival TEXT,
    approved_by TEXT,
    remarks TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    FOREIGN KEY(supplier_id) REFERENCES supplier(supplier_id)
);

CREATE INDEX IF NOT EXISTS idx_purchase_order_status ON purchase_orders(status);
CREATE INDEX IF NOT EXISTS idx_purchase_order_supplier ON purchase_orders(supplier_id);

-- 4. Purchase Order Items
CREATE TABLE IF NOT EXISTS purchase_order_items (
    id TEXT PRIMARY KEY,
    purchase_order_id TEXT NOT NULL,
    ingredient_id TEXT NOT NULL,
    order_qty REAL NOT NULL,
    estimated_cost REAL,
    unit TEXT,
    FOREIGN KEY(purchase_order_id) REFERENCES purchase_orders(id),
    FOREIGN KEY(ingredient_id) REFERENCES ingredients(ingredient_id)
);

CREATE INDEX IF NOT EXISTS idx_purchase_item_order_id ON purchase_order_items(purchase_order_id);

-- 5. Inventory Transactions (Ledger)
CREATE TABLE IF NOT EXISTS inventory_transactions (
    id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    size_ml INTEGER,
    movement_type TEXT CHECK(movement_type IN ('IN', 'OUT', 'ADJUSTMENT', 'PRODUCTION', 'SALES')),
    qty_before INTEGER NOT NULL,
    qty_change INTEGER NOT NULL,
    qty_after INTEGER NOT NULL,
    reference_type TEXT,
    reference_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(product_id) REFERENCES perfume_catalog(perfume_id)
);

CREATE INDEX IF NOT EXISTS idx_inv_tx_product ON inventory_transactions(product_id);
CREATE INDEX IF NOT EXISTS idx_inv_tx_created ON inventory_transactions(created_at);

-- 6. Ingredient Transactions (Ledger)
CREATE TABLE IF NOT EXISTS ingredient_transactions (
    id TEXT PRIMARY KEY,
    ingredient_id TEXT NOT NULL,
    movement_type TEXT CHECK(movement_type IN ('CONSUMPTION', 'PURCHASE', 'ADJUSTMENT')),
    qty_before REAL NOT NULL,
    qty_change REAL NOT NULL,
    qty_after REAL NOT NULL,
    reference_type TEXT,
    reference_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(ingredient_id) REFERENCES ingredients(ingredient_id)
);

CREATE INDEX IF NOT EXISTS idx_ing_tx_ingredient ON ingredient_transactions(ingredient_id);
CREATE INDEX IF NOT EXISTS idx_ing_tx_created ON ingredient_transactions(created_at);
