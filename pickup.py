import sys, json, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core

API = 'https://middle-api.magnit.ru'

STORE_TYPES = ['MM', 'GM', 'DG', 'MO', 'ME', 'DARKSTORE', 'ZARYAD']
STORE_TYPE = 'express'  # сервис самовывоза в корзине/каталоге


def _acc(account):
    accs = core.load_accounts()
    return next((a for a in accs if a.get('name') == account), None)


def _hdrs(acc, at, json_=False):
    h = {**core.dev_headers(acc), 'Authorization': 'bearer ' + at}
    if json_:
        h['Content-Type'] = 'application/json; charset=UTF-8'
    return h


def _call(account, method, path, store_code=None, **kw):
    acc = _acc(account)
    if not acc:
        raise RuntimeError('аккаунт не найден')
    at = core.refresh_magnit_token(acc)
    h = _hdrs(acc, at, json_=kw.get('json') is not None)
    h.update({'x-service': STORE_TYPE, 'x-delivery-type': 'pickup', 'x-app-type': 'OMNI'})
    if store_code:
        h['x-store-code'] = store_code
    r = core.s.request(method, API + path, headers=h, timeout=30, **kw)
    try:
        j = r.json()
    except Exception:
        j = None
    if r.status_code >= 400:
        raise RuntimeError(f'{method} {path} -> {r.status_code}: {r.text[:300]}')
    return j


# ---------- city ----------

def current_city(account):
    return _call(account, 'GET', '/v1/cities/define')


def city_by_fias(account, fias_id):
    return _call(account, 'GET', f'/v1/cities/getbyfiasid?fiasId={fias_id}')


# ---------- stores ----------

def search_stores(account, query='', city_fias_id=None):
    filters = {
        'OpenByWorkingTypes': None,
        'cityFiasId': city_fias_id or None,
        'deliveryTypeList': ['DELIVERY_TYPE_PICKUP'],
        'favorites': False,
        'geo': None,
        'query': query or '',
        'storeTypeList': None,
        'storeTypeListV2': STORE_TYPES,
    }
    body = {
        'filters': filters,
        'pagination': {'offset': 0, 'size': 50},
        'sorting': {'sortBy': 'SORT_BY_GEO', 'sortType': 'SORT_TYPE_ASC'},
    }
    j = _call(account, 'POST', '/v1/stores-facade/search/detail', json=body)
    out = []
    for st in j.get('data', []) or []:
        if not st.get('isActive'):
            continue
        types = st.get('deliveryTypeList') or []
        if 'DELIVERY_TYPE_PICKUP' not in types:
            continue
        hours = pickup_hours(st)
        out.append({
            'code': st['externalId']['storeCode'],
            'owner': st['externalId'].get('owner', 'OWNER_MAGNIT'),
            'name': store_title(st),
            'address': st.get('address', ''),
            'store_type': st.get('storeTypeV2'),
            'latitude': st.get('coordinates', {}).get('latitude'),
            'longitude': st.get('coordinates', {}).get('longitude'),
            'hours': hours,
        })
    return {'data': out, 'totalCount': j.get('totalCount', len(out))}


def store_title(st):
    return st.get('name') or f'Магнит {st.get("storeTypeV2", "")}'.strip()


def pickup_hours(st):
    for t in (st.get('timetableList') or []):
        if t.get('key') == 'WORKING_TIMETABLE_TYPE_PICKUP':
            sched = t.get('value', {}).get('weeklySchedule', {})
            day = sched.get('monday', {}).get('dailySchedule', {})
            if day:
                return f'{day.get("openingTime", "")}-{day.get("closingTime", "")}'
    return ''


def store_detail(account, store_code):
    body = {'externalId': {'owner': 'OWNER_MAGNIT', 'storeCode': store_code}}
    j = _call(account, 'POST', '/v1/stores-facade/store', json=body)
    return {
        'code': store_code,
        'name': store_title(j),
        'address': j.get('address', ''),
        'store_type': j.get('storeTypeV2'),
        'hours': pickup_hours(j),
        'latitude': j.get('coordinates', {}).get('latitude'),
        'longitude': j.get('coordinates', {}).get('longitude'),
    }


# ---------- categories & goods ----------

def categories(account, store_code):
    j = _call(account, 'GET', f'/v3/categories/store/{store_code}?catalogtype=3&storetype={STORE_TYPE}&depth=1')
    out = []

    def walk(items, path):
        for c in items or []:
            name = c.get('name', '')
            p = f'{path} / {name}'.strip(' /')
            out.append({'id': c.get('id'), 'name': name, 'path': p,
                        'image': (c.get('images') or [{}])[0].get('url') if c.get('images') else None})
            walk(c.get('children'), p)
    walk(j.get('items'), '')
    return out


def goods(account, store_code, category_id=None, category_ids=None, term=None, offset=0, limit=20,
          sort_type='popularity', sort_order='desc'):
    cats = []
    for c in (category_ids if category_ids else ([category_id] if category_id is not None else [])):
        try:
            cats.append(int(c))
        except (TypeError, ValueError):
            pass
    base = {
        'catalogType': '3',
        'pagination': {'limit': limit, 'offset': offset},
        'sort': {'order': sort_order, 'type': sort_type},
        'storeCode': store_code,
        'storeType': STORE_TYPE,
        'cityId': '1',
        'token': '',
    }
    if term:
        body = {**base, 'categories': None, 'correctQuery': True, 'dynamicCategory': None,
                'filters': None, 'includeAdultGoods': None, 'offerCategoryIds': None, 'term': term}
    else:
        body = {**base, 'categories': cats,
                'filters': [], 'correctQuery': None, 'dynamicCategory': None,
                'includeAdultGoods': None, 'offerCategoryIds': None, 'term': None}
    j = _call(account, 'POST', '/v2/goods/search', json=body)
    items = []
    for it in j.get('items', []) or []:
        items.append({
            'id': it.get('id'),
            'name': it.get('name', ''),
            'price': it.get('price'),
            'old_price': (it.get('promotion') or {}).get('oldPrice'),
            'discount': (it.get('promotion') or {}).get('discountPercent'),
            'badges': it.get('badges') or [],
            'image': ((it.get('gallery') or [{}])[0].get('url') if it.get('gallery') else None),
            'is_adult': it.get('isForAdults') or it.get('needPassport'),
            'pickup_only': it.get('pickupOnly'),
            'weighted': (it.get('weighted') or {}).get('isWeighted'),
            'weight_step': (it.get('weighted') or {}).get('step'),
            'weight_unit': (it.get('weighted') or {}).get('unitLabel'),
            'qty': it.get('quantity'),
        })
    return {
        'items': items,
        'total_count': (j.get('pagination') or {}).get('totalCount', len(items)),
        'has_more': (j.get('pagination') or {}).get('hasMore', False),
        'next_offset': (j.get('pagination') or {}).get('nextOffset'),
        'category': (j.get('category') or {}).get('title'),
        'category_id': (j.get('category') or {}).get('id'),
        'term': j.get('term') or term,
    }


# ---------- cart ----------

_NAME_CACHE = {}   # (store_code, good_id) -> {'name','price'} (может быть без имени)
_RESOLVED = {}     # account -> {good_id: {'name','price'}} — найденное где-то имя


def _resolve_name(account, good_id, candidates):
    """Название и цена товара: ищет по магазинам-кандидатам; кэш по (account, good_id)."""
    acc_res = _RESOLVED.setdefault(account, {})
    gid = str(good_id)
    if gid in acc_res:
        return acc_res[gid]
    info = {'name': None, 'price': None}
    for st in candidates:
        key = (st, gid)
        cached = _NAME_CACHE.get(key)
        if cached is None:
            cached = {'name': None, 'price': None}
            try:
                r = goods(account, st, term=gid)
                for it in (r.get('items') or []):
                    if str(it.get('id')) == gid:
                        cached = {'name': it.get('name'), 'price': it.get('price')}
                        break
            except Exception:
                pass
            _NAME_CACHE[key] = cached
        if cached.get('name'):
            info = cached
            break
    acc_res[gid] = info
    return info


def _candidate_stores(account, primary):
    """Магазины, где может быть товар: текущий + магазины всех корзин аккаунта."""
    stores = [primary]
    try:
        carts = _call(account, 'GET', '/v1/carts').get('carts') or []
        for c in carts:
            for f in (c.get('formats') or []):
                sc = f.get('storeCode')
                if sc and sc not in stores:
                    stores.append(sc)
    except Exception:
        pass
    return stores[:5]


def enrich_cart(account, cart):
    """Добавляет в позиции корзины goodName и, если нет, catalogPrice."""
    sc = cart.get('storeCode')
    if not sc:
        return cart
    candidates = _candidate_stores(account, sc)
    for it in (cart.get('items') or []):
        if not it.get('qnty'):
            continue
        gid = it.get('goodId')
        if not gid:
            continue
        info = _resolve_name(account, gid, candidates)
        if info['name']:
            it['goodName'] = info['name']
        if 'catalogPrice' not in it and info['price'] is not None:
            it['catalogPrice'] = info['price']
    return cart


def cart(account):
    acc = _acc(account)
    if not acc:
        raise RuntimeError('аккаунт не найден')
    at = core.refresh_magnit_token(acc)
    h = _hdrs(acc, at)
    h['x-delivery-type'] = 'pickup'
    r = core.s.get(f'{API}/v1/carts', headers=h, timeout=30)
    r.raise_for_status()
    j = r.json()
    ex = _express_cart(j.get('carts') or [])
    return {'carts': [ex]} if ex else {'carts': []}


def _express_cart(carts):
    """Корзина самовывоза express; у аккаунта могут быть и другие (cosmetic/dostavka).
    Если express-корзины нет, возвращает None (не подставлять чужую корзину)."""
    for c in carts:
        fmt = c.get('formats') or []
        if any(f.get('service') == STORE_TYPE for f in fmt):
            sc = next((f.get('storeCode') for f in fmt if f.get('service') == STORE_TYPE), None)
            c = {**c, 'storeCode': sc}
            for it in c.get('items') or []:
                inc = it.get('increment') or {}
                it['weighted'] = inc.get('unit') == 'byweight'
                if it['weighted']:
                    it['weight_step'] = inc.get('value')
            return c
    return None


def add_to_cart(account, store_code, items):
    """items: [{'good_id', 'qnty', 'catalog_price'}]"""
    try:
        cur = cart(account)
        cur0 = next((c for c in cur.get('carts', []) if c.get('id')), None)
        if cur0 and cur0.get('storeCode') and cur0['storeCode'] != store_code:
            for it in (cur0.get('items') or []):
                if it.get('goodId'):
                    _resolve_name(account, it['goodId'], [cur0['storeCode']])
    except Exception:
        pass
    _RESOLVED.setdefault(account, {})
    resolved = []
    for it in items:
        gid = str(it['good_id'])
        cp = it.get('catalog_price')
        if cp is None:
            info = _resolve_name(account, gid, [store_code])
            cp = info.get('price')
            if cp is None:
                raise RuntimeError(f'не удалось определить цену товара {gid}')
        if it.get('name') and gid not in _RESOLVED[account]:
            _RESOLVED[account][gid] = {'name': it['name'], 'price': cp}
        resolved.append({'good_id': gid, 'qnty': it.get('qnty', 1), 'catalog_price': cp,
                         'weight_step': it.get('weight_step')})
    req_items = []
    for it in resolved:
        if it.get('weight_step'):
            inc = {'unit': 'byweight', 'value': int(it['weight_step'])}
        else:
            inc = {'unit': 'apiece', 'value': 1}
        req_items.append({
            'goodId': it['good_id'],
            'qnty': int(it['qnty']),
            'addToCartContext': None,
            'catalogPrice': int(it['catalog_price']),
            'createdFromScreen': 'catalog',
            'goodService': STORE_TYPE,
            'goodStoreCode': store_code,
            'increment': inc,
            'modifiers': None,
            'operationType': 'increase',
            'utm': {'utm_campaign': None, 'utm_content': None, 'utm_id': None,
                    'utm_medium': None, 'utm_referrer': None, 'utm_source': None, 'utm_term': None},
        })
    j = _call(account, 'PUT', f'/v2/carts/lite?service={STORE_TYPE}&storeCode={store_code}',
              json={'items': req_items})
    carts = j.get('carts') or []
    return _express_cart(carts) or {'id': None, 'items': []}


def remove_from_cart(account, store_code, good_id, catalog_price=None, qnty=0, weight_step=None):
    """Уменьшает позицию до qnty (абсолютное значение); qnty=0 удаляет из корзины."""
    if weight_step:
        inc = {'unit': 'byweight', 'value': int(weight_step)}
    else:
        inc = {'unit': 'apiece', 'value': 1}
    item = {
        'goodId': str(good_id),
        'qnty': int(qnty or 0),
        'addToCartContext': None,
        'catalogPrice': int(catalog_price or 0),
        'createdFromScreen': 'catalog',
        'goodService': STORE_TYPE,
        'goodStoreCode': store_code,
        'increment': inc,
        'modifiers': None,
        'operationType': 'decrease',
        'utm': {'utm_campaign': None, 'utm_content': None, 'utm_id': None,
                'utm_medium': None, 'utm_referrer': None, 'utm_source': None, 'utm_term': None},
    }
    j = _call(account, 'PUT', f'/v2/carts/lite?service={STORE_TYPE}&storeCode={store_code}',
              json={'items': [item]})
    carts = j.get('carts') or []
    return _express_cart(carts) or {'id': None, 'items': []}


# ---------- checkout & order ----------

def checkout_preview(account, store_code):
    return _call(account, 'GET', '/v1/checkout/preview?needMerge=false&isMarketAvailable=false',
                 store_code=store_code)


def checkout_info(account, cart_id, store_code):
    return _call(account, 'GET', f'/v1/checkout/{cart_id}', store_code=store_code)


def place_order(account, cart_id, store_code, from_iso, to_iso, customer=None,
                payment='StoreOffline', replacement='REPLACE_GOODS', promo_code=None):
    """from_iso/to_iso — локальные ISO-строки слота; серверу нужен UTC."""
    cust = customer or {}
    body = {
        'customer': {'email': cust.get('email'), 'name': None, 'phone': cust.get('phone')},
        'deliveryTimeSlot': [{
            'shipmentId': cart_id,
            'timeslot': {'type': 'timeRange', 'deliveryConfig': None, 'estimatedTime': 0,
                         'id': None,
                         'interval': {'from': to_utc(from_iso), 'to': to_utc(to_iso)},
                         'price': None},
        }],
        'paymentMethod': {'identifier': payment},
        'bonusPoints': None,
        'cartItems': None,
        'delivery': None,
        'detailAddress': {'apartment': None, 'city': None, 'comment': None, 'doorCode': None,
                          'entrance': None, 'floor': None, 'fullAddress': None, 'house': None,
                          'isContactless': False, 'isRover': False, 'latitude': None,
                          'longitude': None, 'street': None},
        'promoCode': promo_code or None,
        'replacementStrategy': {'identifier': replacement},
        'shipments': None,
    }
    return _call(account, 'POST', f'/v1/checkout/{cart_id}/order', store_code=store_code, json=body)


def order_info(account, order_number):
    return _call(account, 'GET', f'/v2/orders/info/{order_number}?lookingForCourier=true')


def active_orders(account):
    """Активные заказы (в работе/готовые к выдаче) для виджета на каталоге."""
    j = _call(account, 'GET', '/v2/orders/active/list?app=loyalty')
    out = []
    for it in j.get('items') or []:
        status = it.get('status') or {}
        summary = it.get('summary') or {}
        header = summary.get('header') or {}
        out.append({
            'order_id': it.get('orderId'),
            'status_code': status.get('code', ''),
            'status_name': status.get('name', ''),
            'status_subtitle': status.get('subtitle', ''),
            'created_at': it.get('createdAt'),
            'total': header.get('formattedValue', ''),
            'items_count': len(it.get('cart') or []),
            'shop_format': (it.get('shop') or {}).get('format', ''),
            'store_name': (it.get('store') or {}).get('name', ''),
            'address': it.get('address', ''),
        })
    return out


def cancel_order(account, order_number, reason='another_reason'):
    """Отмена заказа. Доступна только когда canCancelOrder == true (NEW/ASSEMBLING).
    store_code берём из info заказа. Причины: promo_code_issue, wrong_store,
    unsuitable_delivery_time, wrong_goods, another_address, not_actual,
    long_order_await, another_reason."""
    info = order_info(account, order_number)
    store_code = (info.get('shop') or {}).get('id')
    body = {'reason': reason, 'comment': ''}
    try:
        return _call(account, 'POST', f'/v1/checkout/{order_number}:cancel',
                     store_code=store_code, json=body)
    except RuntimeError as e:
        raise RuntimeError(str(e).replace('422', 'заказ нельзя отменить или отмена недоступна'))


def order_history(account, limit=20):
    """Архив заказов (все: отменённые, выданные и т.п.)."""
    j = _call(account, 'GET', f'/v2/orders/archive/list?limit={limit}')
    out = []
    for it in j.get('items') or []:
        status = it.get('status') or {}
        header = ((it.get('summary') or {}).get('header') or {})
        out.append({
            'order_id': it.get('orderId'),
            'status_code': status.get('code', ''),
            'status_name': status.get('name', ''),
            'created_at': it.get('createdAt'),
            'total': header.get('formattedValue', ''),
            'items_count': len(it.get('cart') or []),
            'address': it.get('address', ''),
        })
    return out


def user_balance(account):
    """Баланс бонусов Магнит Плюс и предупреждения (блокировка и т.п.)."""
    try:
        r = core.s.get('https://middle-api.magnit.ru/v2/user/balance?includeExpiringBalances=false',
                       headers=_hdrs(acc := _acc(account), core.refresh_magnit_token(acc)), timeout=15)
        if r.status_code >= 400:
            try:
                j = r.json()
            except Exception:
                j = {}
            return {'ok': False, 'error': j.get('message') or j.get('title') or f'HTTP {r.status_code}'}
        return {'ok': True, 'data': r.json()}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def coupons(account):
    """Купоны/бонусы пользователя."""
    j = _call(account, 'GET', '/v3/user/coupons/list?limit=20')
    return j.get('coupons') or []


def coupon_by_id(account, coupon_id):
    """Находит купон по favoriteId или коду из items[].couponCode."""
    cid = (coupon_id or '').strip()
    for c in coupons(account):
        if c.get('favoriteId') == cid:
            return c
        for it in (c.get('items') or []):
            if (it.get('couponCode') or '') == cid:
                return c
    return None


def promo_codes(account):
    """Доступные аккаунту промокоды из промо-витрины."""
    j = _call(account, 'GET', '/v1/promo-gallery/promo-shelf')
    return j.get('promocodes') or []


def express_promos(account):
    """Промокоды, действующие на самовывоз express, с правилами применения."""
    j = _call(account, 'GET', '/v2/promo-gallery/promo-codes?service=express&deliveryType=pickup')
    return j.get('promocodes') or []


def check_promo(account, cart_id, store_code, promo_code):
    """Проверяет промокод на корзину без создания заказа.
    Возвращает {applied: bool, reason: str, message: str, promo: dict|None, estimate: dict|None}."""
    code = (promo_code or '').strip().upper()
    if not code:
        return {'applied': False, 'reason': 'empty', 'message': 'Введите промокод', 'promo': None, 'estimate': None}
    promos = express_promos(account)
    promo = next((p for p in promos if (p.get('value') or '').strip().upper() == code), None)
    if not promo:
        return {'applied': False, 'reason': 'not_found', 'message': f'Промокод {code} не найден',
                'promo': None, 'estimate': None}
    try:
        ch = checkout_info(account, cart_id, store_code)
    except Exception:
        ch = {}
    sum_ = ch.get('summary') or {}
    goods_sum = sum_.get('itemsTotalSalePrice') or 0
    discount = 0
    notes = []
    ok = True
    for rule in (promo.get('rules') or []):
        rtype = rule.get('type')
        if rtype == 'MIN_ORDER_SUM':
            min_sum = rule.get('minSum') or 0
            if goods_sum < min_sum:
                ok = False
                notes.append(f'Минимальная сумма заказа — {min_sum / 100:.0f} ₽ (сейчас {goods_sum / 100:.0f} ₽)')
        elif rtype == 'LIST_OF_GOODS':
            notes.append('Скидка действует только на товары из подборки')
        elif rtype == 'FINAL_PRICES':
            notes.append('Промокод не действует на товары с «Финальной ценой» и 18+')
    # оценка скидки: по проценту в заголовке, потолок 2000 ₽
    import re
    m = re.search(r'−?\s*(\d+)%', promo.get('title') or '')
    if m and ok:
        pct = int(m.group(1))
        est = min(int(goods_sum * pct / 100), 200000)
        discount = est
    if not ok:
        return {'applied': False, 'reason': 'rules',
                'message': ' · '.join(notes) or 'Промокод не применим к этой корзине',
                'promo': promo, 'estimate': None}
    return {'applied': True, 'reason': 'ok',
            'message': f'Промокод {code} применён' + (f' — скидка ≈{discount / 100:.0f} ₽' if discount else ''),
            'promo': promo, 'estimate': {'discount': discount, 'goods_sum': goods_sum,
                                         'total_after': max(sum_.get('totalFinalPrice') or 0, goods_sum) - discount}}


# ---------- payment ----------

def payment_methods(account, store_code=None):
    """Способы оплаты аккаунта: привязанные карты, СБП, SberPay."""
    j = _call(account, 'GET', '/v2/payment-methods?withNewPaymentMethods=true&withPayStoreOffline=true',
              store_code=store_code)
    out = []
    for m in (j.get('available') or []):
        out.append({
            'id': m.get('id'),
            'title': m.get('title'),
            'type': m.get('type'),
            'icon_type': m.get('iconType'),
            'payment_flow': m.get('paymentFlow'),
            'payment_mode': m.get('paymentMode'),
            'is_hidden': bool(m.get('isHidden')),
        })
    return {'available': out, 'selected_id': j.get('selectedId')}


def bind_card(account):
    """Запускает привязку карты: возвращает formURL (PayECom) для ввода данных."""
    return _call(account, 'POST', '/v2/payment-methods/cards/bind')


def to_utc(iso):
    from datetime import datetime, timezone
    return datetime.fromisoformat(iso).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ---------- payment ----------

def payment_methods(account, store_code=None):
    """Способы оплаты аккаунта: привязанные карты, СБП, SberPay."""
    j = _call(account, 'GET', '/v2/payment-methods?withNewPaymentMethods=true&withPayStoreOffline=true',
              store_code=store_code)
    out = []
    for m in (j.get('available') or []):
        out.append({
            'id': m.get('id'),
            'title': m.get('title'),
            'type': m.get('type'),
            'icon_type': m.get('iconType'),
            'payment_flow': m.get('paymentFlow'),
            'payment_mode': m.get('paymentMode'),
            'is_hidden': bool(m.get('isHidden')),
        })
    return {'available': out, 'selected_id': j.get('selectedId')}


def bind_card(account):
    """Запускает привязку карты: возвращает formURL (PayECom) для ввода данных."""
    return _call(account, 'POST', '/v2/payment-methods/cards/bind')
