import sys, json, os, time
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


def _call(account, method, path, store_code=None, delivery_type='pickup', address_id=None,
          no_service=False, **kw):
    acc = _acc(account)
    if not acc:
        raise RuntimeError('аккаунт не найден')
    at = core.refresh_magnit_token(acc)
    h = _hdrs(acc, at, json_=kw.get('json') is not None)
    if not no_service:
        h.update({'x-service': STORE_TYPE, 'x-delivery-type': delivery_type, 'x-app-type': 'OMNI'})
    if store_code:
        h['x-store-code'] = store_code
    if address_id:
        h['x-address-id'] = address_id
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


_CITIES_CACHE = {'t': 0, 'data': []}


def all_cities(account):
    if time.time() - _CITIES_CACHE['t'] > 3600:
        try:
            j = _call(account, 'GET', '/v2/cities')
            _CITIES_CACHE['data'] = j.get('cities') or []
            _CITIES_CACHE['t'] = time.time()
        except Exception:
            pass
    return _CITIES_CACHE['data']


def search_cities(account, query='', limit=30):
    q = (query or '').strip().lower()
    cities = all_cities(account)
    if not q:
        out = cities
    else:
        out = [c for c in cities
               if q in (c.get('city') or '').lower()
               or q in (c.get('region') or '').lower()]
        out.sort(key=lambda c: (0 if (c.get('city') or '').lower().startswith(q) else 1))
    return [{'city': c.get('city'), 'cityFiasId': c.get('cityFiasId'),
             'region': c.get('region'), 'area': c.get('area'),
             'isMagnitAvailable': c.get('isMagnitAvailable')} for c in out[:limit]]


# ---------- delivery addresses ----------

def addresses(account):
    """Адресная книга доставки. Каждый адрес: {id, ...attributes}."""
    j = _call(account, 'GET', '/customer_addresses/v1/address_book?pageNumber=1&pageSize=50',
              no_service=True)
    out = []
    for a in (j.get('data') or []):
        attrs = a.get('attributes') or {}
        out.append({
            'id': a.get('id'),
            'country': attrs.get('countryIsoCode'),
            'geo_provider': attrs.get('geoProvider'),
            'house': attrs.get('house'),
            'locality': attrs.get('locality'),
            'province': attrs.get('province'),
            'street': attrs.get('street'),
            'apartment': attrs.get('apartment'),
            'entrance': attrs.get('entrance'),
            'floor': attrs.get('floor'),
            'door_phone': attrs.get('doorPhone'),
            'comment': attrs.get('comment'),
            'district': attrs.get('district'),
            'latitude': attrs.get('latitude'),
            'longitude': attrs.get('longitude'),
            'is_active': bool(attrs.get('isActive')),
            'is_office': bool(attrs.get('isOffice')),
            'full_address': attrs.get('fullFormatted') or attrs.get('shortFormatted'),
        })
    return out


def create_address(account, locality, street, house, latitude, longitude,
                   apartment=None, entrance=None, floor=None, door_phone=None,
                   comment=None, district=None, province='', country='RU',
                   is_active=True):
    """Создаёт адрес доставки в адресной книге. geoProvider=yandex_map — как приложение."""
    attrs = {
        'countryIsoCode': country,
        'fullFormatted': '',
        'geoProvider': 'yandex_map',
        'house': str(house),
        'isActive': is_active,
        'isOffice': False,
        'latitude': float(latitude),
        'locality': locality,
        'longitude': float(longitude),
        'shortFormatted': '',
        'addressTag': None,
        'apartment': apartment,
        'comment': comment,
        'district': district,
        'doorPhone': door_phone,
        'entrance': entrance,
        'floor': floor,
        'province': province,
        'street': street,
    }
    j = _call(account, 'POST', '/customer_addresses/v1/address_book',
              json={'data': {'attributes': attrs, 'type': 'customer_address'}}, no_service=True)
    data = j.get('data') or {}
    addr = {**{k: v for k, v in (data.get('attributes') or {}).items()},
            'id': data.get('id')}
    return addr


def set_active_address(account, address_id, attrs=None):
    """Активирует адрес в адресной книге (PATCH как в приложении)."""
    cur = next((a for a in addresses(account) if a.get('id') == address_id), None)
    if cur is None:
        raise RuntimeError(f'адрес {address_id} не найден в адресной книге')
    body_attrs = {
        'countryIsoCode': cur.get('country') or 'RU',
        'geoProvider': cur.get('geo_provider') or 'yandex_map',
        'house': cur.get('house'),
        'isActive': True,
        'isOffice': cur.get('is_office'),
        'latitude': cur.get('latitude'),
        'locality': cur.get('locality'),
        'longitude': cur.get('longitude'),
        'addressTag': None,
        'apartment': cur.get('apartment') or '',
        'comment': cur.get('comment') or '',
        'district': cur.get('district') or '',
        'doorPhone': cur.get('door_phone') or '',
        'entrance': cur.get('entrance') or '',
        'floor': cur.get('floor'),
        'province': cur.get('province') or '',
        'street': cur.get('street'),
    }
    if attrs:
        body_attrs.update(attrs)
    j = _call(account, 'PATCH', f'/customer_addresses/v1/address_book/{address_id}',
              json={'data': {'attributes': body_attrs, 'id': address_id,
                             'type': 'customer_address'}}, no_service=True)
    return j


# ---------- stores ----------

def search_stores(account, query='', city_fias_id=None, delivery_type='pickup'):
    filters = {
        'OpenByWorkingTypes': None,
        'cityFiasId': city_fias_id or None,
        'deliveryTypeList': ['DELIVERY_TYPE_DELIVERY'] if delivery_type == 'delivery'
        else ['DELIVERY_TYPE_PICKUP'],
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
        want = 'DELIVERY_TYPE_DELIVERY' if delivery_type == 'delivery' else 'DELIVERY_TYPE_PICKUP'
        if want not in types:
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


def _haversine(lat1, lon1, lat2, lon2):
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def delivery_store(account, address_id, city_fias_id=None):
    """Ближайший магазин доставки к адресу (без выбора магазина пользователем)."""
    addr = next((a for a in addresses(account) if a.get('id') == address_id), None)
    if not addr or addr.get('latitude') is None or addr.get('longitude') is None:
        raise RuntimeError('адрес или его координаты не найдены')
    if not city_fias_id:
        try:
            city_fias_id = current_city(account).get('cityFiasId')
        except Exception:
            city_fias_id = None
    stores = search_stores(account, city_fias_id=city_fias_id,
                           delivery_type='delivery').get('data') or []
    with_coord = [s for s in stores if s.get('latitude') is not None and s.get('longitude') is not None]
    if not with_coord:
        raise RuntimeError('в этом городе нет доступных магазинов доставки')
    best = min(with_coord, key=lambda s: _haversine(
        addr['latitude'], addr['longitude'], s['latitude'], s['longitude']))
    best = {**best, 'distance_km': round(_haversine(
        addr['latitude'], addr['longitude'], best['latitude'], best['longitude']), 1)}
    return best


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


def cart(account, delivery_type='pickup', store_code=None):
    acc = _acc(account)
    if not acc:
        raise RuntimeError('аккаунт не найден')
    at = core.refresh_magnit_token(acc)
    h = _hdrs(acc, at)
    h.update({'x-service': STORE_TYPE, 'x-delivery-type': delivery_type, 'x-app-type': 'OMNI'})
    if store_code:
        h['x-store-code'] = store_code
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


def add_to_cart(account, store_code, items, delivery_type='pickup'):
    """items: [{'good_id', 'qnty', 'catalog_price'}]"""
    try:
        cur = cart(account, delivery_type=delivery_type, store_code=store_code)
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
              json={'items': req_items}, delivery_type=delivery_type)
    carts = j.get('carts') or []
    return _express_cart(carts) or {'id': None, 'items': []}


def remove_from_cart(account, store_code, good_id, catalog_price=None, qnty=0, weight_step=None,
                     delivery_type='pickup'):
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
              json={'items': [item]}, delivery_type=delivery_type)
    carts = j.get('carts') or []
    return _express_cart(carts) or {'id': None, 'items': []}


# ---------- checkout & order ----------

def checkout_preview(account, store_code=None, delivery_type='pickup', address_id=None):
    return _call(account, 'GET', '/v1/checkout/preview?needMerge=false&isMarketAvailable=false',
                 store_code=store_code, delivery_type=delivery_type, address_id=address_id)


def checkout_info(account, cart_id, store_code=None, delivery_type='pickup', address_id=None):
    return _call(account, 'GET', f'/v1/checkout/{cart_id}',
                 store_code=store_code, delivery_type=delivery_type, address_id=address_id)


def set_bonus_points(account, cart_id, is_writeoff, store_code=None, delivery_type='pickup',
                     address_id=None):
    """Включает/выключает списание бонусов на корзине checkout."""
    return _call(account, 'PATCH', f'/v1/checkout/{cart_id}/bonus-points',
                 store_code=store_code, delivery_type=delivery_type, address_id=address_id,
                 json={'isWriteOffPoints': bool(is_writeoff)})


def apply_promo(account, promo_code, store_code=None, delivery_type='pickup', address_id=None):
    """Применяет промокод к checkout. Возвращает обновлённый checkout preview."""
    code = (promo_code or '').strip()
    if not code:
        raise RuntimeError('Введите промокод')
    return _call(account, 'PATCH', '/v1/checkout/preview/promo-codes',
                 store_code=store_code, delivery_type=delivery_type, address_id=address_id,
                 json={'value': code})


def place_order(account, cart_id, store_code, from_iso, to_iso, customer=None,
                payment='StoreOffline', replacement='REPLACE_GOODS', promo_code=None,
                delivery_type='pickup', address_id=None):
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
    return _call(account, 'POST', f'/v1/checkout/{cart_id}/order', store_code=store_code,
                 delivery_type=delivery_type, address_id=address_id, json=body)


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


# ---------- loyalty card QR ----------

def loyalty_card(account):
    """Данные бонусной карты: номер identifierNo, статус и ключ TOTP для QR."""
    return _call(account, 'GET', '/v1/user/card')


def totp_now(key_hex, step=300, length=6, clock=None):
    """Код TOTP по RFC 6238 (HMAC-SHA1, ключ в hex). Возвращает строку нужной длины."""
    import hmac, hashlib, struct, time
    t = int(time.time() if clock is None else clock)
    msg = struct.pack('>Q', t // step)
    d = hmac.new(bytes.fromhex(key_hex), msg, hashlib.sha1).digest()
    o = d[-1] & 0x0f
    code = (struct.unpack('>I', d[o:o + 4])[0] & 0x7fffffff) % (10 ** length)
    return str(code).zfill(length)


def card_qr(account):
    """Строка QR бонусной карты: E{identifierNo}T{TOTP-6} + служебная информация."""
    import time
    card = loyalty_card(account)
    totp = card.get('totp') or {}
    key = totp.get('key')
    if not key:
        raise RuntimeError('карта не содержит ключа TOTP для QR')
    step = int(totp.get('step') or 300)
    length = int(totp.get('length') or 6)
    identifier = card.get('identifierNo') or str(card.get('id') or '')
    code = totp_now(key, step=step, length=length)
    return {
        'card': card,
        'identifierNo': identifier,
        'code': code,
        'qr': f'E{identifier}T{code}',
        'step': step,
        'expires_in': step - (int(time.time()) % step),
    }


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


def check_promo(account, cart_id, store_code, promo_code, delivery_type='pickup', address_id=None):
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
        ch = checkout_info(account, cart_id, store_code, delivery_type=delivery_type,
                           address_id=address_id)
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
