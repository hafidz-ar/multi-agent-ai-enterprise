CREATE TRIGGER IF NOT EXISTS update_inventory_status
AFTER UPDATE OF quantity_available ON inventory
FOR EACH ROW
BEGIN
    UPDATE inventory 
    SET status = CASE 
        WHEN NEW.quantity_available = 0 THEN 'OUT_OF_STOCK'
        WHEN NEW.quantity_available <= NEW.reorder_point THEN 'LOW_STOCK'
        ELSE 'AVAILABLE'
    END
    WHERE stock_id = NEW.stock_id;
END;
