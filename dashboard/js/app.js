const API_URL = location.protocol === 'file:' ? 'http://127.0.0.1:8000/api' : '/api';
const DASHBOARD_VERSION = '2.0.0';

// Session persistence via localStorage
function getOrCreateSessionId() {
    let sid = localStorage.getItem('parfum_session_id');
    if (!sid) {
        sid = (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : 'session-' + Date.now();
        localStorage.setItem('parfum_session_id', sid);
    }
    return sid;
}

const SESSION_ID = getOrCreateSessionId();

// Format currency
const formatIDR = (number) => {
    return new Intl.NumberFormat('id-ID', {
        style: 'currency',
        currency: 'IDR',
        minimumFractionDigits: 0
    }).format(number || 0);
};

// Global Caches
let rawInventoryData = [];
let rawIngredientsData = [];
let rawSalesData = [];
let currentInventorySubTab = 'perfumes';

// Global Chart Instances
let salesChartInstance = null;
let revenueChartInstance = null;
let stockDonutChartInstance = null;
let stockBarChartInstance = null;

// Elapsed Timer State
let elapsedTimerInterval = null;

// Initialize Dashboard
document.addEventListener('DOMContentLoaded', () => {
    setupTabNavigation();
    setupSearchFilters();
    setupRevenueFilter();
    setupProcurementFilters();
    setupProductionFilters();
    
    // Preload ALL data
    fetchInventoryStatus();
    fetchSalesAnalytics();
    fetchRevenueAnalytics(1);
    fetchInventoryList();
    fetchIngredientsList();
    fetchSalesList();
    fetchProcurementOrders(1);
    fetchProductionOrders(1);
    fetchAgentMetrics();
    fetchLogs();
    fetchEvaluatorHistory();
    setupEvaluatorEvents();
    
    // Auto-refresh timers
    setInterval(fetchLogs, 10000);
    setInterval(fetchEvaluatorHistory, 10000);
    setInterval(fetchAgentMetrics, 30000);
});

// Tab Navigation Logic
function setupTabNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const pageTitle = document.getElementById('page-title');
    const pageSubtitle = document.getElementById('page-subtitle');
    
    const pageTitles = {
        'dashboard-tab': { title: 'Dashboard Utama', subtitle: 'Monitoring Sistem Multi-Agent AI & Analitik' },
        'inventory-tab': { title: 'Manajemen Inventaris', subtitle: 'Manajemen Stok & Ketersediaan Produk Jadi' },
        'sales-tab': { title: 'Transaksi Penjualan', subtitle: 'Riwayat Transaksi Penjualan Terkini' },
        'procurement-tab': { title: 'Pesanan Pembelian (PO)', subtitle: 'Manajemen Purchase Order (PO) Bahan Baku' },
        'production-tab': { title: 'Pesanan Produksi', subtitle: 'Monitoring Proses Produksi & Batch Resep' },
        'agents-tab': { title: 'Sistem Multi-Agent AI', subtitle: 'Arsitektur, Latensi, & Metrik Langsung Divisi AI' },
        'evaluator-tab': { title: 'Live Evaluator Model', subtitle: 'Uji & Lihat Riwayat Evaluasi LLM-as-a-Judge' }
    };

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            navItems.forEach(n => n.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            
            item.classList.add('active');
            const targetTab = item.getAttribute('data-tab');
            const targetElem = document.getElementById(targetTab);
            if (targetElem) targetElem.classList.add('active');
            
            const mainContent = document.querySelector('.main-content');
            if (mainContent) mainContent.scrollTop = 0;
            
            if (pageTitles[targetTab]) {
                pageTitle.textContent = pageTitles[targetTab].title;
                pageSubtitle.textContent = pageTitles[targetTab].subtitle;
            }
        });
    });
}

// Show Shimmer Skeleton Rows
function showShimmerRows(tbodyId, colCount, rowCount = 4) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;
    tbody.innerHTML = '';
    for (let i = 0; i < rowCount; i++) {
        const tr = document.createElement('tr');
        tr.className = 'shimmer-row';
        let cols = '';
        for (let c = 0; c < colCount; c++) {
            cols += `<td><span style="display:inline-block; width:80%; height:14px; background:rgba(255,255,255,0.08); border-radius:4px;"></span></td>`;
        }
        tr.innerHTML = cols;
        tbody.appendChild(tr);
    }
}

// Show Error Row with Retry
function showTableError(tbodyId, colSpan, message, retryFn) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;
    tbody.innerHTML = `
        <tr>
            <td colspan="${colSpan}" class="text-center" style="padding: 20px; color: var(--danger);">
                <i class="fa-solid fa-triangle-exclamation"></i> ${message} 
                <button class="btn-sm btn-page" style="margin-left: 10px;" onclick="${retryFn}">Coba Lagi</button>
            </td>
        </tr>
    `;
}

// Render Pagination Controls
function renderPagination(containerId, currentPage, totalPages, pageCallbackName) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    let html = `
        <button class="btn-page" ${currentPage <= 1 ? 'disabled' : ''} onclick="${pageCallbackName}(${currentPage - 1})">
            <i class="fa-solid fa-chevron-left"></i> Sebelumnya
        </button>
        <span style="color: var(--text-muted);">Halaman ${currentPage} dari ${totalPages}</span>
        <button class="btn-page" ${currentPage >= totalPages ? 'disabled' : ''} onclick="${pageCallbackName}(${currentPage + 1})">
            Selanjutnya <i class="fa-solid fa-chevron-right"></i>
        </button>
    `;
    container.innerHTML = html;
}

// Fetch Inventory List
async function fetchInventoryList() {
    showShimmerRows('inventory-table-body', 8);
    try {
        const res = await fetch(`${API_URL}/inventory/list`);
        const json = await res.json();
        if (json.status === 'success') {
            rawInventoryData = json.data;
            renderInventoryTable(rawInventoryData);
            renderStockCharts(rawInventoryData);
        } else {
            showTableError('inventory-table-body', 8, 'Gagal memuat inventory.', 'fetchInventoryList()');
        }
    } catch (e) {
        console.error("Error fetching inventory list:", e);
        showTableError('inventory-table-body', 8, 'Koneksi API gagal.', 'fetchInventoryList()');
    }
}

function renderInventoryTable(data) {
    const tbody = document.getElementById('inventory-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    
    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center">Tidak ada data inventory.</td></tr>';
        return;
    }
    
    data.forEach(item => {
        const tr = document.createElement('tr');
        
        let statusClass = 'success';
        let statusText = item.db_status || 'Available';
        
        if (item.quantity_available === 0 || statusText === 'Out of Stock' || statusText === 'OUT_OF_STOCK') {
            statusClass = 'danger';
            statusText = 'Stok Habis';
        } else if (item.quantity_available <= item.reorder_point || statusText === 'Low Stock' || statusText === 'LOW_STOCK') {
            statusClass = 'warning';
            statusText = 'Stok Menipis';
        } else {
            statusClass = 'success';
            statusText = 'Tersedia';
        }
        
        const warehouse = item.warehouse_location || 'Gudang Utama';

        tr.innerHTML = `
            <td><code>${item.perfume_id}</code></td>
            <td><strong>${item.perfume_name}</strong></td>
            <td>${item.size_ml} ml</td>
            <td>${item.quantity_available} pcs</td>
            <td>${item.reorder_point} pcs</td>
            <td>${formatIDR(item.unit_price_idr)}</td>
            <td>${warehouse}</td>
            <td><span class="status ${statusClass}">${statusText}</span></td>
        `;
        tbody.appendChild(tr);
    });
}

// Switch Inventory Sub-Tab (Perfumes vs Ingredients)
function switchInventorySubTab(subTab) {
    currentInventorySubTab = subTab;
    const btnPerfumes = document.getElementById('btn-inventory-perfumes');
    const btnIngredients = document.getElementById('btn-inventory-ingredients');
    const panelPerfumes = document.getElementById('panel-inventory-perfumes');
    const panelIngredients = document.getElementById('panel-inventory-ingredients');

    if (subTab === 'perfumes') {
        if (btnPerfumes) btnPerfumes.classList.add('active');
        if (btnIngredients) btnIngredients.classList.remove('active');
        if (panelPerfumes) panelPerfumes.style.display = 'block';
        if (panelIngredients) panelIngredients.style.display = 'none';
    } else {
        if (btnIngredients) btnIngredients.classList.add('active');
        if (btnPerfumes) btnPerfumes.classList.remove('active');
        if (panelIngredients) panelIngredients.style.display = 'block';
        if (panelPerfumes) panelPerfumes.style.display = 'none';
    }

    const invSearch = document.getElementById('inventory-search');
    if (invSearch) {
        invSearch.dispatchEvent(new Event('input'));
    }
}

// Fetch Ingredients List
async function fetchIngredientsList() {
    showShimmerRows('ingredients-table-body', 8);
    try {
        const res = await fetch(`${API_URL}/ingredients/list`);
        const json = await res.json();
        if (json.status === 'success') {
            rawIngredientsData = json.data;
            renderIngredientsTable(rawIngredientsData);
        } else {
            showTableError('ingredients-table-body', 8, 'Gagal memuat bahan baku.', 'fetchIngredientsList()');
        }
    } catch (e) {
        console.error("Error fetching ingredients list:", e);
        showTableError('ingredients-table-body', 8, 'Koneksi API gagal.', 'fetchIngredientsList()');
    }
}

function renderIngredientsTable(data) {
    const tbody = document.getElementById('ingredients-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    
    if (!data || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center">Tidak ada data bahan baku.</td></tr>';
        return;
    }
    
    data.forEach(item => {
        const tr = document.createElement('tr');
        
        let statusClass = 'success';
        let statusText = item.db_status || 'AVAILABLE';
        
        if (item.stock_available <= 0 || statusText === 'Out of Stock' || statusText === 'OUT_OF_STOCK') {
            statusClass = 'danger';
            statusText = 'Stok Habis';
        } else if (item.stock_available <= item.reorder_point || statusText === 'Low Stock' || statusText === 'LOW_STOCK') {
            statusClass = 'warning';
            statusText = 'Stok Menipis';
        } else {
            statusClass = 'success';
            statusText = 'Tersedia';
        }
        
        tr.innerHTML = `
            <td><code>${item.ingredient_id}</code></td>
            <td><strong>${item.ingredient_name}</strong></td>
            <td><span class="status" style="background:rgba(9,132,227,0.15); color:var(--secondary-light); font-size:11px;">${item.category}</span></td>
            <td><strong>${item.stock_available}</strong> ${item.unit}</td>
            <td>${item.reorder_point} ${item.unit}</td>
            <td>${formatIDR(item.cost_per_unit_idr)}</td>
            <td>${item.origin_country}</td>
            <td><span class="status ${statusClass}">${statusText}</span></td>
        `;
        tbody.appendChild(tr);
    });
}

// Render Dual Stock Analytics Charts
function renderStockCharts(data) {
    if (!data || data.length === 0) return;

    // 1. Donut Chart: Stock per Variant Size
    const sizeMap = {};
    data.forEach(item => {
        const key = `${item.size_ml}ml`;
        sizeMap[key] = (sizeMap[key] || 0) + item.quantity_available;
    });

    const donutCtx = document.getElementById('stockDonutChart');
    if (donutCtx) {
        if (stockDonutChartInstance) stockDonutChartInstance.destroy();
        stockDonutChartInstance = new Chart(donutCtx.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: Object.keys(sizeMap),
                datasets: [{
                    data: Object.values(sizeMap),
                    backgroundColor: ['#00B894', '#0984E3', '#a29bfe', '#FDCB6E'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'right', labels: { color: '#FFFFFF', boxWidth: 12 } }
                }
            }
        });
    }

    // 2. Horizontal Bar Chart: 10 Lowest Stock Items
    const sorted = [...data].sort((a, b) => a.quantity_available - b.quantity_available).slice(0, 10);
    const barLabels = sorted.map(i => `${i.perfume_name} (${i.size_ml}ml)`);
    const barData = sorted.map(i => i.quantity_available);
    const barColors = sorted.map(i => i.quantity_available <= i.reorder_point ? '#D63031' : '#FDCB6E');

    const barCtx = document.getElementById('stockBarChart');
    if (barCtx) {
        if (stockBarChartInstance) stockBarChartInstance.destroy();
        stockBarChartInstance = new Chart(barCtx.getContext('2d'), {
            type: 'bar',
            data: {
                labels: barLabels,
                datasets: [{
                    label: 'Stok',
                    data: barData,
                    backgroundColor: barColors,
                    borderRadius: 4
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#FFFFFF' } },
                    y: { grid: { display: false }, ticks: { color: '#FFFFFF', font: { size: 10 } } }
                }
            }
        });
    }
}

// Fetch Sales List
async function fetchSalesList() {
    showShimmerRows('sales-table-body', 7);
    try {
        const res = await fetch(`${API_URL}/sales/list`);
        const json = await res.json();
        if (json.status === 'success') {
            rawSalesData = json.data;
            renderSalesTable(rawSalesData);
        } else {
            showTableError('sales-table-body', 7, 'Gagal memuat penjualan.', 'fetchSalesList()');
        }
    } catch (e) {
        console.error("Error fetching sales list:", e);
        showTableError('sales-table-body', 7, 'Koneksi API gagal.', 'fetchSalesList()');
    }
}

function renderSalesTable(data) {
    const tbody = document.getElementById('sales-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    
    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center">Tidak ada data penjualan.</td></tr>';
        return;
    }
    
    data.forEach(item => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><code>${item.transaction_id}</code></td>
            <td>${item.date}</td>
            <td><strong>${item.perfume_name}</strong></td>
            <td>${item.quantity} pcs</td>
            <td>${formatIDR(item.total_revenue_idr)}</td>
            <td>${item.customer_city}</td>
            <td><span class="badge">${item.sales_channel}</span></td>
        `;
        tbody.appendChild(tr);
    });
}

// Fetch Procurement Orders (PO)
let currentProcurementPage = 1;
async function fetchProcurementOrders(page = 1) {
    currentProcurementPage = page;
    showShimmerRows('procurement-table-body', 8);

    const status = document.getElementById('procurement-status-filter')?.value || '';
    const supplier = document.getElementById('procurement-search')?.value || '';

    try {
        const query = new URLSearchParams({ page, page_size: 15, status, supplier });
        const res = await fetch(`${API_URL}/procurement/orders?${query}`);
        const json = await res.json();
        
        if (json.status === 'success') {
            renderProcurementTable(json.data);
            const totalPages = Math.ceil(json.total / json.page_size) || 1;
            renderPagination('procurement-pagination', page, totalPages, 'fetchProcurementOrders');
        } else {
            showTableError('procurement-table-body', 8, 'Gagal memuat PO procurement.', 'fetchProcurementOrders(1)');
        }
    } catch (e) {
        console.error("Error fetching procurement orders:", e);
        showTableError('procurement-table-body', 8, 'Koneksi API gagal.', 'fetchProcurementOrders(1)');
    }
}

function getPOProgress(status) {
    switch (status) {
        case 'PENDING':   return { percent: 25, color: '#FDCB6E' };
        case 'APPROVED':  return { percent: 50, color: '#0984E3' };
        case 'ORDERED':   return { percent: 75, color: '#a29bfe' };
        case 'RECEIVED':  return { percent: 100, color: '#00B894' };
        case 'CANCELLED': return { percent: 0, color: '#D63031' };
        default:          return { percent: 10, color: '#636E72' };
    }
}

function renderProcurementTable(data) {
    const tbody = document.getElementById('procurement-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center">Tidak ada data Purchase Order.</td></tr>';
        return;
    }

    data.forEach(item => {
        const tr = document.createElement('tr');
        const prog = getPOProgress(item.status);
        const badgeClass = `badge-${item.status.toLowerCase()}`;

        let actionBtn = `<span style="color: var(--text-muted); font-size:11px;">--</span>`;
        if (item.status === 'PENDING') {
            actionBtn = `<button class="btn-sm btn-approve" onclick="progressPO('${item.id}', 'Setujui PO ini?')"><i class="fa-solid fa-check"></i> Setujui</button>`;
        } else if (item.status === 'APPROVED') {
            actionBtn = `<button class="btn-sm btn-approve" style="background-color: #0984E3;" onclick="progressPO('${item.id}', 'Pesan ke supplier sekarang?')"><i class="fa-solid fa-truck"></i> Pesan</button>`;
        } else if (item.status === 'ORDERED') {
            actionBtn = `<button class="btn-sm btn-approve" style="background-color: #00B894;" onclick="progressPO('${item.id}', 'Tandai bahan baku telah diterima?')"><i class="fa-solid fa-box-open"></i> Terima</button>`;
        }

        // Build the ingredients list display
        let ingredientsHTML = '';
        if (item.items && item.items.length > 0) {
            const displayItems = item.items.slice(0, 2); // show up to 2 items directly
            const extraCount = item.items.length - 2;
            
            const itemList = displayItems.map(i => `<div style="font-size: 12px; margin-bottom: 2px;">• ${i.ingredient_name} <span class="text-muted">(${i.order_qty} ${i.unit})</span></div>`).join('');
            
            ingredientsHTML = itemList;
            if (extraCount > 0) {
                ingredientsHTML += `<div style="font-size: 11px; color: var(--text-muted);">+ ${extraCount} bahan lainnya</div>`;
            }
        } else {
            ingredientsHTML = `<span style="font-size: 12px; color: var(--text-muted);">${item.total_items} bahan</span>`;
        }

        tr.innerHTML = `
            <td><code>${item.po_number}</code></td>
            <td><strong>${item.supplier_name}</strong></td>
            <td><span class="status ${badgeClass}">${item.status}</span></td>
            <td>
                <div class="progress-bar-container">
                    <div class="progress-bar-fill" style="width: ${prog.percent}%; background-color: ${prog.color};"></div>
                </div>
                <span style="font-size:11px; color:var(--text-muted);">${prog.percent}%</span>
            </td>
            <td>${ingredientsHTML}</td>
            <td>${formatIDR(item.estimated_cost)}</td>
            <td>${item.created_at || '-'}</td>
            <td>${actionBtn}</td>
        `;
        tbody.appendChild(tr);
    });
}

// Progress Purchase Order Action with Confirmation
async function progressPO(poId, confirmMsg) {
    if (!confirm(confirmMsg || `Apakah Anda yakin ingin melanjutkan proses PO ini?`)) {
        return;
    }
    try {
        const res = await fetch(`${API_URL}/procurement/orders/${poId}/progress`, {
            method: 'PATCH'
        });
        const json = await res.json();
        if (json.status === 'success') {
            fetchProcurementOrders(currentProcurementPage);
        } else if (json.status === 'info') {
            alert(json.message);
        } else {
            alert(`Gagal memproses PO: ${json.detail || 'Terjadi kesalahan.'}`);
        }
    } catch (e) {
        console.error("Error progressing PO:", e);
        alert("Gagal terhubung ke server.");
    }
}

// Fetch Production Orders
let currentProductionPage = 1;
async function fetchProductionOrders(page = 1) {
    currentProductionPage = page;
    showShimmerRows('production-table-body', 8);

    const status = document.getElementById('production-status-filter')?.value || '';
    const product = document.getElementById('production-search')?.value || '';

    try {
        const query = new URLSearchParams({ page, page_size: 15, status, product });
        const res = await fetch(`${API_URL}/production/orders?${query}`);
        const json = await res.json();

        if (json.status === 'success') {
            renderProductionTable(json.data);
            const totalPages = Math.ceil(json.total / json.page_size) || 1;
            renderPagination('production-pagination', page, totalPages, 'fetchProductionOrders');
        } else {
            showTableError('production-table-body', 8, 'Gagal memuat produksi.', 'fetchProductionOrders(1)');
        }
    } catch (e) {
        console.error("Error fetching production orders:", e);
        showTableError('production-table-body', 8, 'Koneksi API gagal.', 'fetchProductionOrders(1)');
    }
}

function renderProductionTable(data) {
    const tbody = document.getElementById('production-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center">Tidak ada data Production Order.</td></tr>';
        return;
    }

    data.forEach(item => {
        const tr = document.createElement('tr');
        const badgeClass = `badge-${item.status.toLowerCase()}`;

        tr.innerHTML = `
            <td><code>${item.production_no}</code></td>
            <td><strong>${item.perfume_name}</strong></td>
            <td>${item.variant_id} ml</td>
            <td>${item.qty_requested} pcs</td>
            <td>${item.qty_produced || 0} pcs</td>
            <td><span class="status ${badgeClass}">${item.status}</span></td>
            <td><i class="fa-solid fa-stopwatch" style="font-size:10px; color:var(--text-muted);"></i> ${item.duration}</td>
            <td>${item.created_at || '-'}</td>
        `;
        tbody.appendChild(tr);
    });
}

// Fetch Live Agent Metrics
async function fetchAgentMetrics() {
    try {
        const res = await fetch(`${API_URL}/agents/metrics`);
        const json = await res.json();
        
        if (json.status === 'success') {
            const metrics = json.data;
            Object.keys(metrics).forEach(agName => {
                const data = metrics[agName];
                const latElem = document.getElementById(`lat-${agName}`);
                const callsElem = document.getElementById(`calls-${agName}`);
                const lastElem = document.getElementById(`last-${agName}`);
                const errElem = document.getElementById(`err-${agName}`);

                if (latElem) latElem.textContent = `${data.avg_latency_ms} ms`;
                if (callsElem) callsElem.textContent = data.total_calls;
                if (errElem) {
                    errElem.textContent = `${data.error_rate}%`;
                    errElem.style.color = data.error_rate > 5 ? 'var(--danger)' : 'var(--primary-light)';
                }
                if (lastElem) {
                    if (data.last_call_ago_seconds !== null) {
                        const s = data.last_call_ago_seconds;
                        if (s < 60) lastElem.textContent = `${s} detik yg lalu`;
                        else if (s < 3600) lastElem.textContent = `${Math.floor(s/60)} menit yg lalu`;
                        else if (s < 86400) lastElem.textContent = `${Math.floor(s/3600)} jam yg lalu`;
                        else lastElem.textContent = `${Math.floor(s/86400)} hari yg lalu`;
                    } else {
                        lastElem.textContent = 'Belum ada';
                    }
                }
            });
        }
    } catch (e) {
        console.error("Error fetching agent metrics:", e);
    }
}

// Setup Filters
function setupSearchFilters() {
    const invSearch = document.getElementById('inventory-search');
    if (invSearch) {
        invSearch.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            if (currentInventorySubTab === 'perfumes') {
                const filtered = rawInventoryData.filter(item => 
                    item.perfume_name.toLowerCase().includes(query) || 
                    item.perfume_id.toLowerCase().includes(query)
                );
                renderInventoryTable(filtered);
            } else {
                const filtered = rawIngredientsData.filter(item => 
                    item.ingredient_name.toLowerCase().includes(query) || 
                    item.ingredient_id.toLowerCase().includes(query) ||
                    item.category.toLowerCase().includes(query) ||
                    item.origin_country.toLowerCase().includes(query)
                );
                renderIngredientsTable(filtered);
            }
        });
    }

    const salesSearch = document.getElementById('sales-search');
    if (salesSearch) {
        salesSearch.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            const filtered = rawSalesData.filter(item => 
                item.perfume_name.toLowerCase().includes(query) || 
                item.transaction_id.toLowerCase().includes(query) ||
                item.customer_city.toLowerCase().includes(query)
            );
            renderSalesTable(filtered);
        });
    }
}

function setupRevenueFilter() {
    const filterSelect = document.getElementById('revenue-filter');
    if (filterSelect) {
        filterSelect.addEventListener('change', (e) => {
            fetchRevenueAnalytics(parseInt(e.target.value, 10));
        });
    }
}

function setupProcurementFilters() {
    const statusFilter = document.getElementById('procurement-status-filter');
    const searchInput = document.getElementById('procurement-search');

    if (statusFilter) statusFilter.addEventListener('change', () => fetchProcurementOrders(1));
    if (searchInput) searchInput.addEventListener('input', () => fetchProcurementOrders(1));
}

function setupProductionFilters() {
    const statusFilter = document.getElementById('production-status-filter');
    const searchInput = document.getElementById('production-search');

    if (statusFilter) statusFilter.addEventListener('change', () => fetchProductionOrders(1));
    if (searchInput) searchInput.addEventListener('input', () => fetchProductionOrders(1));
}

// Fetch Inventory Status Top Cards
async function fetchInventoryStatus() {
    try {
        const res = await fetch(`${API_URL}/inventory/status`);
        const json = await res.json();
        
        if (json.status === 'success') {
            document.getElementById('total-products').textContent = json.data.total_products;
            document.getElementById('total-revenue').textContent = formatIDR(json.data.total_revenue);
            document.getElementById('low-stock').textContent = json.data.low_stock;
            document.getElementById('out-of-stock').textContent = json.data.out_of_stock;
        }
    } catch (e) {
        console.error("Error fetching inventory status:", e);
    }
}

// Fetch Top 5 Sales Bar Chart
async function fetchSalesAnalytics() {
    try {
        const res = await fetch(`${API_URL}/analytics/sales`);
        const json = await res.json();
        
        if (json.status === 'success') {
            const labels = json.data.map(item => item.name);
            const data = json.data.map(item => item.sold);
            
            const ctx = document.getElementById('salesChart').getContext('2d');
            if (salesChartInstance) salesChartInstance.destroy();
            
            const gradient = ctx.createLinearGradient(0, 0, 0, 400);
            gradient.addColorStop(0, '#55EFC4');
            gradient.addColorStop(1, '#00856A');
            
            salesChartInstance = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{ label: 'Jumlah Terjual', data: data, backgroundColor: gradient, borderRadius: 5 }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#FFFFFF' } },
                        x: { grid: { display: false }, ticks: { color: '#FFFFFF', callback: function(val) { const l = this.getLabelForValue(val); return l.length > 12 ? l.substr(0,12)+'...' : l; } } }
                    }
                }
            });
        }
    } catch (e) {
        console.error("Error fetching sales analytics:", e);
    }
}

// Fetch Revenue Analytics Line Chart
async function fetchRevenueAnalytics(months = 1) {
    try {
        const res = await fetch(`${API_URL}/analytics/revenue?months=${months}`);
        const json = await res.json();
        
        if (json.status === 'success') {
            const labels = json.data.map(item => item.month);
            const data = json.data.map(item => item.revenue);
            
            const ctx = document.getElementById('revenueChart').getContext('2d');
            if (revenueChartInstance) revenueChartInstance.destroy();
            
            revenueChartInstance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Pendapatan (IDR)',
                        data: data,
                        borderColor: '#0984E3',
                        backgroundColor: 'rgba(9, 132, 227, 0.15)',
                        borderWidth: 2,
                        pointBackgroundColor: '#00CFFF',
                        pointRadius: months === 1 ? 3 : 5,
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: 'rgba(255,255,255,0.05)' },
                            ticks: { color: '#FFFFFF', callback: (val) => 'Rp ' + (val / 1000000).toFixed(0) + 'M' }
                        },
                        x: { 
                            grid: { display: false }, 
                            ticks: { 
                                color: '#FFFFFF',
                                maxTicksLimit: months === 1 ? 10 : 12
                            } 
                        }
                    }
                }
            });
        }
    } catch (e) {
        console.error("Error fetching revenue analytics:", e);
    }
}

// Fetch Evaluation Logs
async function fetchLogs() {
    try {
        const res = await fetch(`${API_URL}/logs`);
        const json = await res.json();
        
        if (json.status === 'success') {
            const tbody = document.getElementById('log-body');
            if (!tbody) return;
            tbody.innerHTML = '';
            
            if (json.data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-center">Belum ada log evaluasi.</td></tr>';
                return;
            }
            
            json.data.forEach(logLine => {
                const timeMatch = logLine.match(/^\[(.*?)\]/);
                const timestamp = timeMatch ? timeMatch[1] : '';
                const agentMatch = logLine.match(/AGENT=(.*?)(?:\s*\||$)/);
                const agent = agentMatch ? agentMatch[1] : 'Unknown';
                const inputMatch = logLine.match(/INPUT="(.*?)"/);
                const input = inputMatch ? inputMatch[1] : '';
                const statusMatch = logLine.match(/STATUS=(.*?)(?:\s*\||$)/);
                const status = statusMatch ? statusMatch[1] : 'OK';
                
                const tr = document.createElement('tr');
                const isSuccess = status.includes('SUCCESS') || status.includes('OK');
                const statusClass = isSuccess ? 'success' : 'error';
                const statusLabel = isSuccess ? 'SUCCESS' : 'ERROR';
                
                const inputSnippet = input.length > 40 ? input.substring(0, 40) + '...' : input;
                const timeDisplay = timestamp.includes(' ') ? timestamp.split(' ')[1] : timestamp;
                
                tr.innerHTML = `
                    <td>${timeDisplay}</td>
                    <td>${agent}</td>
                    <td title="${input}">${inputSnippet}</td>
                    <td><span class="status ${statusClass}">${statusLabel}</span></td>
                `;
                tbody.appendChild(tr);
            });
        }
    } catch (e) {
        console.error("Error fetching logs:", e);
    }
}

const refreshLogsBtn = document.getElementById('refresh-logs');
if (refreshLogsBtn) refreshLogsBtn.addEventListener('click', fetchLogs);

// Chat & Adaptive Elapsed Timer Logic
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const chatMessages = document.getElementById('chat-messages');

function scrollToBottom() {
    setTimeout(() => {
        if (chatMessages) {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }, 50);
}

function startElapsedTimer(elementId) {
    stopElapsedTimer();
    const startTime = Date.now();
    elapsedTimerInterval = setInterval(() => {
        const elem = document.getElementById(elementId);
        if (!elem) return;
        const elapsedSec = ((Date.now() - startTime) / 1000).toFixed(1);
        const extraMsg = elapsedSec > 15 ? ' — memakan waktu lebih lama dari biasanya...' : '';
        elem.innerHTML = `
            <div class="avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="bubble"><i class="fa-solid fa-circle-notch fa-spin"></i> Memproses dengan AI Multi-Agent...<div class="elapsed-timer"><i class="fa-solid fa-clock"></i> Waktu berjalan: ${elapsedSec}s${extraMsg}</div></div>
        `;
    }, 100);
}

function stopElapsedTimer() {
    if (elapsedTimerInterval) {
        clearInterval(elapsedTimerInterval);
        elapsedTimerInterval = null;
    }
}

function formatAgentResponse(text) {
    if (!text) return '';
    if (text.includes('--- System Coordinator ---')) {
        let content = text.replace('--- System Coordinator ---\n', '');
        return content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/^- (.*$)/gim, '<li>$1</li>')
            .replace(/\n/g, '<br>');
    }
    return text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
}

function appendMessage(sender, text) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${sender}`;
    
    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'avatar';
    avatarDiv.innerHTML = sender === 'agent' ? '<i class="fa-solid fa-robot"></i>' : '<i class="fa-solid fa-user"></i>';
    
    const bubbleDiv = document.createElement('div');
    bubbleDiv.className = 'bubble';
    
    if (sender === 'agent' && text.includes('---')) {
        bubbleDiv.innerHTML = formatAgentResponse(text);
    } else {
        bubbleDiv.innerHTML = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
    }
    
    msgDiv.appendChild(avatarDiv);
    msgDiv.appendChild(bubbleDiv);
    
    chatMessages.appendChild(msgDiv);
    scrollToBottom();
}

// Smart Event-Driven Refresh
function triggerSmartRefresh(responseText) {
    const txt = (responseText || '').toLowerCase();
    
    // Always refresh logs & agent metrics
    fetchLogs();
    fetchAgentMetrics();

    // Event-driven targeted refresh
    if (txt.includes('reorder') || txt.includes('produksi') || txt.includes('purchase order') || txt.includes('stok')) {
        fetchInventoryStatus();
        fetchInventoryList();
        fetchProcurementOrders(1);
        fetchProductionOrders(1);
    } else if (txt.includes('beli') || txt.includes('pesanan') || txt.includes('berhasil dibuat')) {
        fetchInventoryStatus();
        fetchInventoryList();
        fetchSalesList();
    }
}

async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;
    
    appendMessage('user', text);
    chatInput.value = '';
    
    chatInput.disabled = true;
    sendBtn.disabled = true;
    
    const loadingId = 'loading-' + Date.now();
    const loadingMsg = document.createElement('div');
    loadingMsg.className = 'message agent';
    loadingMsg.id = loadingId;
    chatMessages.appendChild(loadingMsg);
    scrollToBottom();

    startElapsedTimer(loadingId);
    
    try {
        const res = await fetch(`${API_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: text,
                session_id: SESSION_ID,
                client_timestamp: new Date().toISOString(),
                dashboard_version: DASHBOARD_VERSION
            })
        });
        
        stopElapsedTimer();
        const json = await res.json();
        
        const loadingElem = document.getElementById(loadingId);
        if (loadingElem) loadingElem.remove();
        
        if (json.status === 'success') {
            appendMessage('agent', json.response);
            triggerSmartRefresh(json.response);
        } else {
            appendMessage('agent', `Error: ${json.response}`);
        }
    } catch (e) {
        stopElapsedTimer();
        const loadingElem = document.getElementById(loadingId);
        if (loadingElem) loadingElem.remove();
        appendMessage('agent', `Connection error: Pastikan backend FastAPI sedang berjalan.`);
    } finally {
        chatInput.disabled = false;
        sendBtn.disabled = false;
        chatInput.focus();
    }
}

if (sendBtn) sendBtn.addEventListener('click', sendMessage);
if (chatInput) {
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
}

// ==========================================
// Evaluator Model Logic
// ==========================================

async function fetchEvaluatorHistory() {
    try {
        const res = await fetch(`${API_URL}/evaluator/history`);
        const json = await res.json();
        
        const tbody = document.getElementById('evaluator-table-body');
        if (!tbody) return;
        
        if (json.status === 'success') {
            tbody.innerHTML = '';
            if (json.data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="text-center">Belum ada riwayat evaluasi.</td></tr>';
                return;
            }
            
            json.data.forEach(item => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${item.question}"><strong>${item.question}</strong></td>
                    <td style="font-size: 0.85em; color: var(--text-muted);">${item.created_at}</td>
                    <td><strong>${item.accuracy_score}/10</strong></td>
                    <td><strong>${item.explainability_score}/10</strong></td>
                    <td><strong>${item.hallucination_score}/10</strong></td>
                    <td><strong>${item.efficiency_score}/10</strong></td>
                `;
                tbody.appendChild(tr);
            });
        }
    } catch (e) {
        console.error("Error fetching evaluator history:", e);
    }
}

function setupEvaluatorEvents() {
    const clearBtn = document.getElementById('btn-clear-eval-history');
    
    if (clearBtn) {
        clearBtn.addEventListener('click', async () => {
            if (confirm("Apakah Anda yakin ingin menghapus SEMUA riwayat evaluasi? Tindakan ini tidak bisa dibatalkan.")) {
                try {
                    const res = await fetch(`${API_URL}/evaluator/history`, {
                        method: 'DELETE'
                    });
                    const json = await res.json();
                    if (json.status === 'success') {
                        fetchEvaluatorHistory();
                    } else {
                        alert("Gagal menghapus riwayat.");
                    }
                } catch (e) {
                    console.error("Error deleting history:", e);
                    alert("Koneksi gagal saat menghapus riwayat.");
                }
            }
        });
    }
}
