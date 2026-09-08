const amountStyles = document.createElement('style');
amountStyles.textContent = '.amount-input{padding:12px 16px 12px 48px!important;background-position:16px center!important}.profile{margin-left:64px!important;background-image:url("/assets/assets/icon-login.svg")!important;background-position:center!important;background-size:20px!important;background-repeat:no-repeat!important}.catalog-toggle{background-image:none!important;gap:8px!important}.catalog-toggle span{transform:none!important}.catalog-toggle>img{width:20px;height:20px;flex:0 0 20px}.service,.product{transition:transform .18s ease,box-shadow .18s ease,outline-color .18s ease}.service:hover{transform:translateY(-3px)}.service:hover .service-icon img{box-shadow:0 8px 16px rgba(20,40,80,.22)}.product:hover:not(:disabled){transform:translateY(-4px);outline:2px solid #268bf3;box-shadow:0 16px 30px rgba(20,40,80,.18)}.product:disabled{cursor:not-allowed;opacity:.6}';
document.head.append(amountStyles);

const $ = selector => document.querySelector(selector);
const currencyRates = { '₽': 1, '$': 86.5857, '₸': 0.161 };
let currentCurrency = localStorage.getItem('storefront-currency') || '₽';
let selectedProduct = null, catalogProducts = [], catalogOpen = false, slide = 0;
let searchText = '', selectedKind = '', drawerOrder = null, timer = null;

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || 'Попробуйте ещё раз');
  return data;
}
function money(rubles) { const value = rubles / currencyRates[currentCurrency]; const digits = currentCurrency === '$' ? 2 : 0; return `${new Intl.NumberFormat('ru-RU', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value)} ${currentCurrency}`; }
function escapeHtml(value) { const node = document.createElement('span'); node.textContent = String(value); return node.innerHTML; }
function productsForView() { const needle = searchText.toLowerCase(); return catalogProducts.filter(product => (!needle || product.name.toLowerCase().includes(needle)) && (!selectedKind || product.kind === selectedKind)); }
function renderProduct(product) { const soldOut = !product.in_stock; return `<button class="product" data-sku="${escapeHtml(product.sku)}" ${soldOut ? 'disabled' : ''}><div class="product-cover"></div><div class="product-info"><div class="product-kind">${escapeHtml(product.name)}</div><div class="product-price">${money(product.price)} <small>${money(Math.round(product.price * 1.5))}</small></div><span class="product-buy">${soldOut ? 'Распродано' : 'Купить'}</span></div></button>`; }
function wireGrid(grid) { grid.onclick = event => { const card = event.target.closest('.product:not(:disabled)'); if (card) openPurchase(catalogProducts.find(product => product.sku === card.dataset.sku)); }; }
function renderCatalog() { const cards = productsForView().map(renderProduct).join('') || '<p class="form-message">Ничего не найдено.</p>'; ['#productGrid', '#recommendedGrid', '#otherGrid'].forEach(selector => { const grid = $(selector); if (grid) { grid.innerHTML = cards; wireGrid(grid); } }); if (selectedProduct && !drawerOrder) { const fresh = catalogProducts.find(product => product.sku === selectedProduct.sku); if (fresh && !$('#purchaseDrawer').hidden) { selectedProduct = fresh; $('#drawerPrice').textContent = money(fresh.price); } } }

function checkoutKey(sku) { return `keywave-checkout-${sku}`; }
function orderId() { return `checkout_${(crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}${Math.random()}`).replaceAll('-', '')}`.slice(0, 64); }
function resetDrawer() { clearInterval(timer); drawerOrder = null; $('#promoInput').closest('label').hidden = false; $('#createOrder').textContent = 'Создать заказ'; $('#purchaseMessage').textContent = ''; }
function timeLeft(expiresAt) { const seconds = Math.max(0, Math.ceil((new Date(expiresAt).getTime() - Date.now()) / 1000)); return { seconds, text: `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}` }; }
function showReservation(order) {
  drawerOrder = order;
  $('#promoInput').closest('label').hidden = true;
  $('#createOrder').textContent = 'Перейти к оплате';
  $('#drawerPrice').textContent = money(order.amount);
  clearInterval(timer);
  const tick = () => {
    const left = timeLeft(order.reservation_expires_at);
    $('#purchaseMessage').textContent = `Товар забронирован. Осталось ${left.text}`;
    if (!left.seconds) { resetDrawer(); sessionStorage.removeItem(checkoutKey(order.sku)); $('#purchaseMessage').textContent = 'Бронь закончилась — товар снова доступен.'; loadProducts(); }
  };
  tick(); timer = setInterval(tick, 500);
}
async function resumeReservation(product) { const raw = sessionStorage.getItem(checkoutKey(product.sku)); if (!raw) return; try { const order = await api(`/api/orders/${JSON.parse(raw).order_id}`); if (order.status === 'reserved') showReservation(order); else sessionStorage.removeItem(checkoutKey(product.sku)); } catch { sessionStorage.removeItem(checkoutKey(product.sku)); } }
function openPurchase(product) { if (!product || !product.in_stock) return; selectedProduct = product; resetDrawer(); $('#drawerTitle').textContent = product.name; $('#drawerPrice').textContent = money(product.price); $('#purchaseDrawer').hidden = false; resumeReservation(product); }
async function reserveOrPay() {
  const button = $('#createOrder'); button.disabled = true;
  try {
    if (drawerOrder) {
      location.href = `/order.html?id=${encodeURIComponent(drawerOrder.id)}`;
      return;
    }
    let savedId; try { savedId = JSON.parse(sessionStorage.getItem(checkoutKey(selectedProduct.sku))).order_id; } catch { savedId = null; }
    savedId ||= orderId(); sessionStorage.setItem(checkoutKey(selectedProduct.sku), JSON.stringify({ order_id: savedId }));
    $('#purchaseMessage').textContent = 'Резервируем товар…';
    const order = await api('/api/orders', { method: 'POST', body: JSON.stringify({ sku: selectedProduct.sku, promo_code: $('#promoInput').value || null, order_id: savedId }) });
    if (order.status !== 'reserved') throw new Error('Этот товар больше недоступен. Выберите другой.');
    showReservation(order);
  } catch (error) { if (!drawerOrder && selectedProduct) sessionStorage.removeItem(checkoutKey(selectedProduct.sku)); $('#purchaseMessage').textContent = error.message; } finally { button.disabled = false; }
}

function mountFigmaIcons() {
  $('#catalogToggle').innerHTML = '<img src="/assets/assets/icon-catalog.svg" alt=""><span>Каталог</span>';
  const icons = ['tab-donate.svg', 'tab-subscribes.svg', 'tab-items.svg', 'tab-accounts.svg', 'tab-keys.svg', 'tab-currency.svg', 'tab-other.svg'];
  document.querySelectorAll('.category-tabs button').forEach((button, index) => { const label = button.textContent.replace(/^[^\p{L}]*/u, '').trim(); button.innerHTML = `<img src="/assets/assets/${icons[index]}" alt="">${label}`; });
  const login = $('.steam-form label input'); if (login) login.placeholder = 'Логин Steam';
  const promo = $('.promo'); if (promo) promo.innerHTML = 'Ввести промокод<img src="/assets/assets/icon-chevron.svg" alt="">';
  const more = $('.service.more .service-icon'); if (more) more.innerHTML = '<img src="/assets/assets/icon-more.svg" alt="">';
  const previous = $('#previousSlide'), next = $('#nextSlide'); if (previous) previous.innerHTML = '<img src="/assets/assets/icon-arrow-prev.svg" alt="">'; if (next) next.innerHTML = '<img src="/assets/assets/icon-arrow-next.svg" alt="">';
}
function mountCatalogMenu() {
  const menu = $('#catalogMenu'); if (!menu) return;
  const arrow = '/assets/assets/catalog-arrow.svg', activeArrow = '/assets/assets/catalog-arrow-active.svg', headingArrow = '/assets/assets/catalog-heading-arrow.svg';
  const category = (label, active = false) => `<button class="${active ? 'active' : ''}"><span>${label}</span><img src="${active ? activeArrow : arrow}" alt=""></button>`;
  const group = (title, items, curated = false) => `<div class="catalog-group ${curated ? 'catalog-curated' : ''}"><h3>${title}<img src="${headingArrow}" alt=""></h3>${items.map(item => `<a>${item}</a>`).join('')}</div>`;
  menu.innerHTML = `<div class="catalog-inner"><nav class="catalog-sidebar">${category('Игры и игровые сервисы', true)}${category('Игровые ценности')}${category('Мобильные игры')}${category('Сервисы и соцсети')}${category('Программы')}</nav><section class="catalog-columns">${group('Steam', ['Игры и DLC', 'Пополнение баланса', 'Подарочные карты', 'Коллекционные карточки', 'Смена региона'])}${group('PlayStation', ['Игры и DLC', 'Пополнение баланса', 'Новые аккаунты', 'PS Plus', 'EA Play'])}${group('Xbox', ['Игры и DLC', 'Пополнение баланса', 'Новые аккаунты', 'Xbox Game Pass', 'Услуги'])}${group('Nintendo', ['Игры и DLC', 'Подарочные карты', 'Новые аккаунты', 'NS Online'])}${group('Battle.net', ['World of Warcraft', 'Подарочные карты', 'Прямое пополнение', 'Новые аккаунты', 'Смена региона'])}${group('Подборки', ['Скидки 90%', 'Популярные издатели', 'Лучшие серии игр', 'Steam Deck', 'Bundle-наборы'], true)}</section></div>`;
}
function updateCurrencyUI() { document.querySelectorAll('.currency').forEach(button => button.classList.toggle('selected', button.dataset.currency === currentCurrency)); const amount = $('.amount-input input'); if (amount) amount.value = money(500); const pay = $('#steamAction'); if (pay) pay.textContent = `Оплатить ${money(500)}`; renderCatalog(); }
async function loadProducts() { catalogProducts = await api('/api/products'); updateCurrencyUI(); }
function setCatalogOpen(open) { catalogOpen = open; $('#catalogMenu').hidden = !catalogOpen; }
function updateUrl() { const url = new URL(location.href); searchText ? url.searchParams.set('q', searchText) : url.searchParams.delete('q'); selectedKind ? url.searchParams.set('kind', selectedKind) : url.searchParams.delete('kind'); history.replaceState({}, '', url); }
function connectCatalogEvents() { const events = new EventSource('/api/events/catalog'); events.addEventListener('catalog', event => { try { catalogProducts = JSON.parse(event.data); renderCatalog(); } catch { loadProducts(); } }); }

$('#catalogToggle').onclick = () => setCatalogOpen(!catalogOpen); document.addEventListener('click', event => { if (!event.target.closest('.topbar')) setCatalogOpen(false); });
document.querySelectorAll('.currency').forEach(button => button.onclick = () => { currentCurrency = button.dataset.currency; localStorage.setItem('storefront-currency', currentCurrency); updateCurrencyUI(); });
$('#steamAction').onclick = () => openPurchase(catalogProducts.find(product => product.kind === 'topup'));
$('.close-drawer').onclick = () => { resetDrawer(); $('#purchaseDrawer').hidden = true; }; $('#createOrder').onclick = reserveOrPay;
const search = $('.search input'); const initialFilters = new URLSearchParams(location.search); searchText = initialFilters.get('q') || ''; selectedKind = initialFilters.get('kind') || ''; search.value = searchText; let searchDelay; search.oninput = () => { clearTimeout(searchDelay); searchDelay = setTimeout(() => { searchText = search.value.trim(); updateUrl(); renderCatalog(); }, 150); }; $('.search').onsubmit = event => { event.preventDefault(); searchText = search.value.trim(); updateUrl(); renderCatalog(); };
const kinds = ['', 'subscription', '', '', 'key', 'topup', '']; document.querySelectorAll('.category-tabs button').forEach((button, index) => { button.classList.toggle('active', kinds[index] === selectedKind || (!selectedKind && index === 0)); button.onclick = () => { document.querySelectorAll('.category-tabs button').forEach(item => item.classList.remove('active')); button.classList.add('active'); selectedKind = kinds[index]; updateUrl(); renderCatalog(); }; });
const showSlide = next => { const slides = document.querySelectorAll('.hero-slide'), dots = document.querySelectorAll('.dot'); slide = (next + slides.length) % slides.length; slides.forEach((item, index) => item.classList.toggle('is-active', index === slide)); dots.forEach((item, index) => item.classList.toggle('active', index === slide)); };
$('#previousSlide').onclick = () => showSlide(slide - 1); $('#nextSlide').onclick = () => showSlide(slide + 1);
mountFigmaIcons(); mountCatalogMenu(); loadProducts().catch(() => document.querySelectorAll('.product-grid').forEach(grid => grid.innerHTML = '<p class="form-message">Не удалось загрузить каталог.</p>')); connectCatalogEvents();
