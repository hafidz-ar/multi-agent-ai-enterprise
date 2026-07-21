import urllib.request, json

endpoints = [
    ('inventory/status', 'GET'),
    ('analytics/sales', 'GET'),
    ('analytics/revenue', 'GET'),
    ('inventory/list', 'GET'),
    ('sales/list', 'GET'),
    ('logs', 'GET'),
]

BASE = 'http://127.0.0.1:8000/api'

print("=" * 60)
print("  CEK SEMUA ENDPOINT API DASHBOARD")
print("=" * 60)

for path, method in endpoints:
    url = f"{BASE}/{path}"
    try:
        res = urllib.request.urlopen(url, timeout=5)
        data = json.loads(res.read())
        status = data.get('status', '?')
        if path == 'inventory/list':
            count = len(data.get('data', []))
            sample = data['data'][0] if count > 0 else {}
            print(f"  OK  /{path}: {count} rows | Sample: {sample.get('perfume_name', '')[:30]}")
        elif path == 'sales/list':
            count = len(data.get('data', []))
            sample = data['data'][0] if count > 0 else {}
            print(f"  OK  /{path}: {count} rows | Sample: {sample.get('perfume_name', '')[:30]}")
        elif path == 'analytics/sales':
            rows = data.get('data', [])
            top = rows[0] if rows else {}
            print(f"  OK  /{path}: Top = {top.get('name','')[:25]} ({top.get('sold',0)} sold)")
        elif path == 'analytics/revenue':
            rows = data.get('data', [])
            print(f"  OK  /{path}: {len(rows)} bulan data, terbaru={rows[-1] if rows else 'N/A'}")
        elif path == 'inventory/status':
            d = data.get('data', {})
            print(f"  OK  /{path}: Products={d.get('total_products')} | LowStock={d.get('low_stock')} | OoS={d.get('out_of_stock')}")
        elif path == 'logs':
            count = len(data.get('data', []))
            print(f"  OK  /{path}: {count} log entries")
    except Exception as e:
        print(f"  ERR /{path}: {e}")

print("=" * 60)
print("  SELESAI")
print("=" * 60)
