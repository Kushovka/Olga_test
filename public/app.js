const amountStyles=document.createElement('style'); amountStyles.textContent='.amount-input{padding:12px 16px 12px 48px!important;background-position:16px center!important}.profile{margin-left:64px!important;background-image:url("/assets/assets/icon-login.svg")!important;background-position:center!important;background-size:20px!important;background-repeat:no-repeat!important}.catalog-toggle{background-image:none!important;gap:8px!important}.catalog-toggle span{transform:none!important}.catalog-toggle>img{width:20px;height:20px;flex:0 0 20px}.service,.product{transition:transform .18s ease,box-shadow .18s ease,outline-color .18s ease}.service:hover{transform:translateY(-3px)}.service:hover .service-icon img{box-shadow:0 8px 16px rgba(20,40,80,.22)}.product:hover{transform:translateY(-4px);outline:2px solid #268bf3;box-shadow:0 16px 30px rgba(20,40,80,.18)}'; document.head.append(amountStyles);
const $ = selector => document.querySelector(selector);
const currencyRates = {'₽':1,'$':86.5857,'₸':0.161};
let currentCurrency = localStorage.getItem('storefront-currency') || '₽';
let selectedProduct = null, catalogProducts = [];
async function api(path, options = {}) { const response = await fetch(path, {headers:{'Content-Type':'application/json'},...options}); const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'Попробуйте ещё раз'); return data; }
function money(rubles, old = false) { const value = rubles / currencyRates[currentCurrency]; const digits = currentCurrency === '$' ? 2 : 0; return `${new Intl.NumberFormat('ru-RU',{minimumFractionDigits:digits,maximumFractionDigits:digits}).format(value)} ${currentCurrency}`; }
function renderProduct(product) { return `<button class="product" data-sku="${product.sku}"><div class="product-cover"></div><div class="product-info"><div class="product-kind">${product.name}</div><div class="product-price">${money(990)} <small>${money(1990,true)}</small></div><span class="product-buy">Купить</span></div></button>`; }
function openPurchase(product) { selectedProduct=product; $('#drawerTitle').textContent=product.name; $('#drawerPrice').textContent=money(product.price); $('#purchaseDrawer').hidden=false; }
function wireGrid(grid) { grid.onclick = event => { const card=event.target.closest('.product'); if (card) openPurchase(catalogProducts.find(product=>product.sku===card.dataset.sku)); }; }
function renderCatalog() { const cards=catalogProducts.map(renderProduct).join(''); ['#productGrid','#recommendedGrid','#otherGrid'].forEach(selector=>{const grid=$(selector); if(grid){grid.innerHTML=cards;wireGrid(grid);}}); }
function mountFigmaIcons() {
  $('#catalogToggle').innerHTML='<img src="/assets/assets/icon-catalog.svg" alt=""><span>Каталог</span>';
  const icons=['tab-donate.svg','tab-subscribes.svg','tab-items.svg','tab-accounts.svg','tab-keys.svg','tab-currency.svg','tab-other.svg'];
  document.querySelectorAll('.category-tabs button').forEach((button,index)=>{
    const label=button.textContent.replace(/^[^\p{L}]*/u,'').trim();
    button.innerHTML=`<img src="/assets/assets/${icons[index]}" alt="">${label}`;
  });
  const login=$('.steam-form label input');
  if(login) login.placeholder='Логин Steam';
  const promo=$('.promo');
  if(promo) promo.innerHTML='Ввести промокод<img src="/assets/assets/icon-chevron.svg" alt="">';
  const more=$('.service.more .service-icon');
  if(more) more.innerHTML='<img src="/assets/assets/icon-more.svg" alt="">';
  const previous=$('#previousSlide'), next=$('#nextSlide');
  if(previous) previous.innerHTML='<img src="/assets/assets/icon-arrow-prev.svg" alt="">';
  if(next) next.innerHTML='<img src="/assets/assets/icon-arrow-next.svg" alt="">';
}
function mountCatalogMenu() {
  const menu=$('#catalogMenu');
  if(!menu) return;
  const arrow='/assets/assets/catalog-arrow.svg', activeArrow='/assets/assets/catalog-arrow-active.svg', headingArrow='/assets/assets/catalog-heading-arrow.svg';
  const category=(label,active=false)=>`<button class="${active?'active':''}"><span>${label}</span><img src="${active?activeArrow:arrow}" alt=""></button>`;
  const group=(title,items,curated=false)=>`<div class="catalog-group ${curated?'catalog-curated':''}"><h3>${title}<img src="${headingArrow}" alt=""></h3>${items.map(item=>`<a>${item}</a>`).join('')}</div>`;
  menu.innerHTML=`<div class="catalog-inner"><nav class="catalog-sidebar">${category('Игры и игровые сервисы',true)}${category('Игровые ценности')}${category('Мобильные игры')}${category('Сервисы и соцсети')}${category('Программы')}</nav><section class="catalog-columns">${group('Steam',['Игры и DLC','Пополнение баланса','Подарочные карты','Коллекционные карточки','Смена региона'])}${group('PlayStation',['Игры и DLC','Пополнение баланса','Новые аккаунты','PS Plus','EA Play'])}${group('Xbox',['Игры и DLC','Пополнение баланса','Новые аккаунты','Xbox Game Pass','Услуги'])}${group('Nintendo',['Игры и DLC','Подарочные карты','Новые аккаунты','NS Online'])}${group('Battle.net',['World of Warcraft','Подарочные карты','Прямое пополнение','Новые аккаунты','Смена региона'])}${group('Подборки',['Скидки 90%','Популярные издатели','Лучшие серии игр','Steam Deck','Bundle-наборы'],true)}</section></div>`;
}
function updateCurrencyUI() { document.querySelectorAll('.currency').forEach(button=>button.classList.toggle('selected',button.dataset.currency===currentCurrency)); const topupAmount=$('.amount-input input'); if(topupAmount) topupAmount.value=money(500); const pay=$('#steamAction'); if(pay) pay.textContent=`Оплатить ${money(500)}`; renderCatalog(); if(selectedProduct && !$('#purchaseDrawer').hidden) $('#drawerPrice').textContent=money(selectedProduct.price); }
async function loadProducts(){ catalogProducts=await api('/api/products'); updateCurrencyUI(); }
let catalogOpen=false;
function setCatalogOpen(open) { catalogOpen=open; $('#catalogMenu').hidden=!catalogOpen; }
$('#catalogToggle').onclick=()=>setCatalogOpen(!catalogOpen);
document.addEventListener('click',event=>{if(!event.target.closest('.topbar')) setCatalogOpen(false);});
document.querySelectorAll('.currency').forEach(button=>button.onclick=()=>{currentCurrency=button.dataset.currency;localStorage.setItem('storefront-currency',currentCurrency);updateCurrencyUI();});
$('#steamAction').onclick=()=>{const topup=catalogProducts.find(product=>product.kind==='topup');if(topup)openPurchase(topup);};
$('.close-drawer').onclick=()=>$('#purchaseDrawer').hidden=true;
$('#createOrder').onclick=async()=>{const message=$('#purchaseMessage');message.textContent='Создаём заказ…';try{const order=await api('/api/orders',{method:'POST',body:JSON.stringify({sku:selectedProduct.sku,promo_code:$('#promoInput').value||null})});location.href=`/order.html?id=${encodeURIComponent(order.id)}`;}catch(error){message.textContent=error.message;}};
let slide=0;const showSlide=next=>{const slides=document.querySelectorAll('.hero-slide'),dots=document.querySelectorAll('.dot');slide=(next+slides.length)%slides.length;slides.forEach((item,index)=>item.classList.toggle('is-active',index===slide));dots.forEach((item,index)=>item.classList.toggle('active',index===slide));};$('#previousSlide').onclick=()=>showSlide(slide-1);$('#nextSlide').onclick=()=>showSlide(slide+1);mountFigmaIcons();mountCatalogMenu();
loadProducts().catch(()=>document.querySelectorAll('.product-grid').forEach(grid=>grid.innerHTML='<p class="form-message">Не удалось загрузить каталог.</p>'));
