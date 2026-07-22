import os
import random
import pandas as pd
import numpy as np
from faker import Faker
from datetime import datetime, timedelta

# Initialize Faker for Indonesia
fake = Faker('id_ID')
Faker.seed(42)
random.seed(42)
np.random.seed(42)

# Configuration
NUM_PERFUMES = 30
NUM_INGREDIENTS = 40
NUM_SUPPLIERS = 80
NUM_SALES = 100

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'raw')
os.makedirs(DATA_DIR, exist_ok=True)

# 1. Generate Ingredients
def generate_ingredients():
    categories = ['Citrus', 'Floral', 'Woody', 'Musk', 'Resin', 'Spice', 'Fruity', 'Herbal']
    ingredients = []
    
    ingredient_names = [
        "Bergamot Oil", "Lemon Extract", "Rose Absolute", "Jasmine Essence", "Sandalwood", 
        "Cedarwood", "White Musk", "Ambergris", "Vanilla Extract", "Patchouli",
        "Oud Wood", "Vetiver", "Lavender", "Orange Blossom", "Ylang Ylang",
        "Cardamom", "Cinnamon", "Black Pepper", "Tonka Bean", "Frankincense",
        "Neroli", "Grapefruit", "Mandarin", "Iris", "Tuberose",
        "Geranium", "Violet Leaf", "Oakmoss", "Myrrh", "Benzoin",
        "Pink Pepper", "Coriander", "Ginger", "Nutmeg", "Clove",
        "Rosemary", "Thyme", "Basil", "Mint", "Sage",
        "Pine", "Cypress", "Juniper", "Balsam", "Galbanum",
        "Peach", "Plum", "Apple", "Pear", "Berry",
        "Coconut", "Fig", "Melon", "Pineapple", "Mango",
        "Papaya", "Guava", "Passionfruit", "Lychee", "Pomegranate",
        "Raspberry", "Strawberry", "Blackberry", "Blueberry", "Cranberry",
        "Cherry", "Apricot", "Nectarine", "Mandarin Orange", "Tangerine",
        "Clementine", "Yuzu", "Kumquat", "Pomelo", "Lime",
        "Petitgrain", "Lemongrass", "Citronella", "Verbena", "Palmarosa"
    ]
    
    # Pad if not enough names
    while len(ingredient_names) < NUM_INGREDIENTS:
        ingredient_names.append(f"Synthetic {fake.word().capitalize()} Note")
        
    for i in range(NUM_INGREDIENTS):
        ing_id = f"ING-{i+1:03d}"
        stock = random.randint(500, 5000)
        reorder = random.randint(100, 500)
        
        ingredients.append({
            'ingredient_id': ing_id,
            'ingredient_name': ingredient_names[i],
            'category': random.choice(categories),
            'unit': random.choice(['ml', 'gram']),
            'stock_available': stock,
            'reorder_point': reorder,
            'cost_per_unit_idr': random.randint(10, 500) * 1000,
            'origin_country': fake.country(),
            'status': 'Available' if stock > reorder else ('Low' if stock > 0 else 'Out of Stock')
        })
        
    df = pd.DataFrame(ingredients)
    df.to_csv(os.path.join(DATA_DIR, 'ingredients.csv'), index=False)
    return df

# 2. Generate Suppliers
def generate_suppliers(ingredients_df):
    suppliers = []
    
    for i in range(NUM_SUPPLIERS):
        sup_id = f"SUP-{i+1:03d}"
        ing_row = ingredients_df.sample(1).iloc[0]
        
        suppliers.append({
            'supplier_id': sup_id,
            'supplier_name': fake.company(),
            'country': fake.country(),
            'ingredient_id': ing_row['ingredient_id'],
            'ingredient_name': ing_row['ingredient_name'],
            'price_per_unit_idr': int(ing_row['cost_per_unit_idr'] * random.uniform(0.8, 1.2)),
            'min_order_quantity': random.choice([50, 100, 200, 500]),
            'lead_time_days': random.randint(3, 30),
            'reliability_score': round(random.uniform(5.0, 10.0), 1),
            'payment_terms': random.choice(['Net 30', 'Net 60', 'COD', 'Prepaid']),
            'contact_email': fake.company_email(),
            'last_transaction_date': fake.date_between(start_date='-1y', end_date='today')
        })
        
    df = pd.DataFrame(suppliers)
    df.to_csv(os.path.join(DATA_DIR, 'supplier.csv'), index=False)
    return df

# 3. Generate Perfume Catalog
def generate_perfumes():
    brands = ['Chanel', 'Dior', 'Gucci', 'YSL', 'Hermès', 'Burberry', 'Tom Ford', 'Jo Malone', 'Byredo', 'Le Labo']
    categories = ['Floral', 'Woody', 'Fresh', 'Oriental', 'Aquatic', 'Gourmand']
    genders = ['Male', 'Female', 'Unisex']
    concentrations = ['EDT', 'EDP', 'Parfum', 'EDC']
    seasons = ['Spring', 'Summer', 'Fall', 'Winter', 'All Season']
    occasions = ['Casual', 'Office', 'Date', 'Formal', 'Sport']
    
    perfumes = []
    
    for i in range(NUM_PERFUMES):
        perf_id = f"PRF-{i+1:03d}"
        brand = random.choice(brands)
        name = f"{brand} {fake.word().capitalize()} {random.choice(['Intense', 'Aqua', 'Noir', 'Lumiere', 'Absolu', 'Oud', 'Flora', ''])}".strip()
        
        # Descriptions in Indonesian
        desc_templates = [
            f"{name} adalah parfum {random.choice(categories).lower()} yang elegan dari {brand}. Cocok digunakan untuk {random.choice(occasions).lower()} dengan ketahanan yang sangat baik.",
            f"Hadir dengan aroma mewah, {name} memadukan keharuman segar dan hangat. Pilihan tepat bagi Anda yang mencari kesan berkelas.",
            f"Rasakan sensasi premium dari {brand} dengan {name}. Diciptakan khusus untuk menemani aktivitas harian Anda dengan aroma yang memikat.",
            f"Sebuah mahakarya wewangian. {name} membawa karakter berani namun tetap lembut, direkomendasikan untuk penggunaan di musim {random.choice(seasons).lower()}."
        ]
        
        base_price = random.randint(50, 500) * 10000
        
        perfumes.append({
            'perfume_id': perf_id,
            'name': name,
            'brand': brand,
            'category': random.choice(categories),
            'gender': random.choice(genders),
            'top_notes': f"{fake.word().capitalize()}, {fake.word().capitalize()}",
            'heart_notes': f"{fake.word().capitalize()}, {fake.word().capitalize()}",
            'base_notes': f"{fake.word().capitalize()}, {fake.word().capitalize()}",
            'concentration': random.choice(concentrations),
            'longevity_hours': random.randint(3, 12),
            'sillage': random.choice(['Intimate', 'Moderate', 'Strong', 'Enormous']),
            'season': random.choice(seasons),
            'occasion': random.choice(occasions),
            'price_idr': base_price,
            'description': random.choice(desc_templates),
            'rating': round(random.uniform(3.5, 5.0), 1),
        })
        
    df = pd.DataFrame(perfumes)
    df.to_csv(os.path.join(DATA_DIR, 'perfume_catalog.csv'), index=False)
    return df

# 4. Generate Inventory
def generate_inventory(perfumes_df):
    inventory = []
    sizes = [50, 100]
    
    for idx, row in perfumes_df.iterrows():
        for size in sizes:
            qty = random.randint(0, 500)
            reorder = random.randint(20, 100)
            
            inventory.append({
                'stock_id': f"STK-{row['perfume_id']}-{size}",
                'perfume_id': row['perfume_id'],
                'perfume_name': row['name'],
                'size_ml': size,
                'quantity_available': qty,
                'reorder_point': reorder,
                'status': 'Available' if qty > reorder else ('Low Stock' if qty > 0 else 'Out of Stock'),
                'last_updated': fake.date_between(start_date='-1m', end_date='today'),
                'warehouse_location': random.choice(['Gudang Jakarta', 'Gudang Surabaya', 'Gudang Bandung'])
            })
            
    df = pd.DataFrame(inventory)
    df.to_csv(os.path.join(DATA_DIR, 'inventory.csv'), index=False)
    return df

# 5. Generate Formula
def generate_formula(perfumes_df, ingredients_df):
    formulas = []
    
    for idx, prow in perfumes_df.iterrows():
        num_ingredients = random.randint(3, 7)
        sampled_ings = ingredients_df.sample(num_ingredients)
        
        percentages = np.random.dirichlet(np.ones(num_ingredients), size=1)[0] * 100
        percentages = np.round(percentages).astype(int)
        percentages[-1] = 100 - np.sum(percentages[:-1])
        
        for j, (i_idx, irow) in enumerate(sampled_ings.iterrows()):
            formulas.append({
                'formula_id': f"FOR-{prow['perfume_id']}",
                'perfume_id': prow['perfume_id'],
                'perfume_name': prow['name'],
                'ingredient_id': irow['ingredient_id'],
                'ingredient_name': irow['ingredient_name'],
                'percentage': int(percentages[j]),
                'quantity_per_100ml': int(percentages[j]), # Assuming 100ml total for simplicity
                'note_type': random.choice(['Top', 'Heart', 'Base', 'Fixative']),
                'is_critical': random.choice([True, False])
            })
            
    df = pd.DataFrame(formulas)
    df.to_csv(os.path.join(DATA_DIR, 'formula.csv'), index=False)
    return df

# 6. Generate Sales History
def generate_sales(perfumes_df):
    sales = []
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 12, 31)
    date_range = (end_date - start_date).days
    
    for i in range(NUM_SALES):
        prow = perfumes_df.sample(1).iloc[0]
        size = random.choice([50, 100])
        qty = random.randint(1, 5)
        price_multiplier = 1.0 if size == 50 else 1.8
        unit_price = int(prow['price_idr'] * price_multiplier)
        
        sale_date = start_date + timedelta(days=random.randint(0, date_range))
        
        sales.append({
            'transaction_id': f"TRX-{i+1:06d}",
            'date': sale_date.strftime('%Y-%m-%d'),
            'perfume_id': prow['perfume_id'],
            'perfume_name': prow['name'],
            'category': prow['category'],
            'size_ml': size,
            'quantity_sold': qty,
            'unit_price_idr': unit_price,
            'total_revenue_idr': qty * unit_price,
            'channel': random.choice(['Online', 'Offline', 'Wholesale']),
            'region': random.choice(['Jakarta', 'Surabaya', 'Bandung', 'Medan', 'Bali']),
            'customer_segment': random.choice(['Regular', 'VIP', 'Corporate']),
            'campaign_id': random.choice([f"CMP-{random.randint(1, 10):03d}", None, None]),
            'return_flag': random.random() < 0.02 # 2% return rate
        })
        
    df = pd.DataFrame(sales)
    # Sort by date
    df = df.sort_values(by='date')
    df.to_csv(os.path.join(DATA_DIR, 'sales_history.csv'), index=False)
    return df

# 7. Generate FAQ and SOP
def generate_faq_sop():
    content = """# FAQ & SOP Pelayanan Pelanggan - Enterprise Parfum

## BAGIAN 1: STANDAR OPERASIONAL PROSEDUR (SOP) CUSTOMER SERVICE

### Tujuan
Memberikan panduan bagi agen Customer Service dalam melayani pelanggan dengan ramah, profesional, dan informatif, khususnya dalam merekomendasikan produk parfum.

### Prosedur Rekomendasi Parfum
1. **Sapaan Awal**: "Selamat pagi/siang/sore, selamat datang di layanan pelanggan kami. Ada yang bisa saya bantu terkait pemilihan parfum Anda hari ini?"
2. **Analisis Kebutuhan**:
   - Tanyakan preferensi aroma pelanggan (misalnya: segar, manis, kayu-kayuan, atau bunga).
   - Tanyakan tujuan penggunaan parfum (misalnya: untuk bekerja, kencan, acara formal, atau santai).
   - Tanyakan anggaran atau budget (opsional, jika relevan).
3. **Pemberian Rekomendasi**:
   - Berikan 2-3 pilihan parfum yang paling sesuai dengan jawaban pelanggan.
   - Jelaskan Notes (Top, Heart, Base) dari masing-class parfum tersebut.
   - Sebutkan ketahanan aroma (Longevity) dan jejak aroma (Sillage).
4. **Penutupan**: "Apakah ada informasi lain yang Anda butuhkan? Terima kasih telah berbelanja bersama kami."

### Kebijakan Retur & Garansi
1. Pelanggan dapat mengajukan retur produk dalam waktu maksimal 7 hari setelah barang diterima.
2. Syarat retur: Segel belum dibuka, botol tidak pecah atau rusak, dan menyertakan video unboxing.
3. Proses pengembalian dana memakan waktu 3-5 hari kerja setelah barang retur diterima di gudang kami.

---

## BAGIAN 2: PANDUAN NOTES PARFUM & GLOSARIUM

### Panduan Notes Parfum (Piramida Aroma)
- **Top Notes (Aroma Pembuka)**: Aroma yang pertama kali tercium saat parfum disemprotkan. Biasanya bertahan selama 15-30 menit. Contoh bahan: Citrus (Lemon, Bergamot), Fruity (Berry), Herbal.
- **Heart Notes (Aroma Tengah)**: Aroma inti dari parfum yang muncul setelah Top Notes memudar. Menjadi karakter utama parfum dan bertahan hingga 2-4 jam. Contoh bahan: Floral (Rose, Jasmine), Spice (Cinnamon).
- **Base Notes (Aroma Dasar)**: Aroma penutup yang paling tahan lama dan menempel di kulit atau pakaian. Bertahan hingga berjam-jam bahkan seharian. Contoh bahan: Woody (Sandalwood, Cedar), Musk, Vanilla, Patchouli.

### Glosarium Istilah Teknis
- **Sillage (Jejak Aroma)**: Seberapa jauh aroma parfum menyebar di udara saat pemakainya berjalan melintas. (Kategori: Intimate, Moderate, Strong, Enormous).
- **Longevity (Ketahanan)**: Seberapa lama wangi parfum bertahan di kulit pemakai.
- **EDC (Eau de Cologne)**: Konsentrasi minyak wangi terendah (2-5%), bertahan 1-2 jam.
- **EDT (Eau de Toilette)**: Konsentrasi menengah (5-15%), cocok untuk siang hari, bertahan 3-5 jam.
- **EDP (Eau de Parfum)**: Konsentrasi tinggi (15-20%), sangat populer, bertahan 5-8 jam.
- **Parfum (Extrait de Parfum)**: Konsentrasi tertinggi (20-30%+), sangat tahan lama, bisa lebih dari 12 jam.
- **Blind Buy**: Membeli parfum tanpa pernah mencium aromanya terlebih dahulu (biasanya karena membaca review atau melihat notes).
- **Decant**: Parfum yang dipindahkan dari botol asli ke botol kecil (sample) untuk memudahkan dibawa atau dicoba.

---

## BAGIAN 3: FREQUENTLY ASKED QUESTIONS (FAQ) PELANGGAN

Q: Bagaimana cara memilih parfum yang cocok untuk saya?
A: Pemilihan parfum sangat personal. Mulailah dengan mengenali aroma yang Anda sukai di keseharian (misal bau jeruk, bau bunga mawar, atau aroma kayu segar). Lalu, tentukan parfum tersebut akan dipakai untuk situasi apa. Jika Anda menyukai aroma segar, carilah kategori Citrus atau Aquatic.

Q: Apa perbedaan antara EDP dan EDT?
A: Perbedaannya terletak pada konsentrasi minyak pewangi. EDP (Eau de Parfum) memiliki konsentrasi 15-20% sehingga wanginya lebih tahan lama (5-8 jam) dan intens. Sedangkan EDT (Eau de Toilette) memiliki konsentrasi 5-15% yang lebih ringan, segar, dan bertahan sekitar 3-5 jam, cocok untuk pemakaian sehari-hari.

Q: Mengapa wangi parfum di kulit saya berbeda dengan di kertas tester?
A: Wangi parfum bereaksi dengan pH kulit, suhu tubuh, dan hormon alami setiap orang. Hal ini menyebabkan sebuah parfum bisa tercium sedikit berbeda pada tiap individu dibandingkan saat disemprot pada kertas tester.

Q: Bagaimana cara agar wangi parfum lebih tahan lama?
A: Semprotkan parfum di titik-titik nadi tubuh seperti pergelangan tangan, leher, dan belakang telinga. Kulit di area ini lebih hangat dan membantu menyebarkan aroma. Selain itu, pastikan kulit dalam keadaan lembap (sehabis mandi atau memakai lotion *unscented*) sebelum menyemprotkan parfum. Jangan menggosok pergelangan tangan setelah menyemprotkan parfum karena dapat merusak molekul aroma (Top Notes).

Q: Parfum apa yang cocok untuk digunakan di kantor?
A: Untuk lingkungan profesional, disarankan memilih parfum dengan aroma yang tidak terlalu menyengat atau *sillage* moderate. Kategori Floral yang lembut, Fresh, atau Citrus adalah pilihan aman yang tidak akan mengganggu rekan kerja.

Q: Apakah parfum bisa kadaluarsa?
A: Secara teknis, parfum tidak memiliki tanggal kadaluarsa tetap, namun kualitas aromanya dapat menurun setelah 3-5 tahun. Tanda parfum telah rusak adalah perubahan warna menjadi lebih gelap, atau aromanya menjadi asam/menyengat seperti cuka.

Q: Bagaimana cara menyimpan parfum yang benar?
A: Simpan botol parfum Anda di tempat yang sejuk, kering, dan terhindar dari paparan sinar matahari langsung, seperti di dalam lemari pakaian. Jangan menyimpan parfum di kamar mandi karena perubahan suhu dan kelembapan dapat merusak kualitas parfum.

Q: Apakah saya bisa mencampur dua parfum yang berbeda (Layering)?
A: Tentu saja! Layering adalah cara yang menyenangkan untuk menciptakan aroma unik atau *signature scent* Anda sendiri. Tips dasar layering: semprotkan parfum dengan aroma lebih kuat/berat terlebih dahulu (misal Woody/Spicy), kemudian timpa dengan parfum yang lebih ringan (misal Citrus/Fruity).

Q: Parfum saya wanginya sudah tidak tercium lagi oleh saya setelah beberapa jam, apakah parfumnya tidak awet?
A: Hal ini sering disebut "Nose Blindness" atau *Olfactory Fatigue*. Hidung Anda sudah terbiasa dengan aroma tersebut secara konstan sehingga berhenti mendeteksinya. Namun, orang lain di sekitar Anda kemungkinan besar masih bisa mencium wangi parfum Anda.
"""
    with open(os.path.join(DATA_DIR, 'faq_sop.txt'), 'w', encoding='utf-8') as f:
        f.write(content)
        
    print(f"Generated faq_sop.txt")

if __name__ == "__main__":
    print("Starting dataset generation...")
    
    print("Generating ingredients...")
    ing_df = generate_ingredients()
    
    print("Generating suppliers...")
    generate_suppliers(ing_df)
    
    print("Generating perfumes...")
    perf_df = generate_perfumes()
    
    print("Generating inventory...")
    generate_inventory(perf_df)
    
    print("Generating formula...")
    generate_formula(perf_df, ing_df)
    
    print("Generating sales history...")
    generate_sales(perf_df)
    
    print("Generating FAQ & SOP...")
    generate_faq_sop()
    
    print("Dataset generation completed successfully in data/raw/")
