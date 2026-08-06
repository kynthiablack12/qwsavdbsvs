"""Перенос данных на Railway (PostgreSQL + Volume).

Запуск локально, когда уже создан PostgreSQL в Railway:

    $env:DATABASE_URL="postgres://user:pass@host:port/db"
    python migrate_data.py

Что делает:
  1. переносит призы из локального prizes.db в таблицу prizes в PostgreSQL;
  2. копирует accounts.json / sessions.json / coupon_shares.json в DATA_DIR
     (на Railway это каталог Volume, env DATA_DIR=/data).

Если DATABASE_URL не задан — только копирование JSON (для локальной проверки).
"""
import os, sys, json, sqlite3, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import core


def migrate_prizes():
    if not core.USE_PG:
        print('DATABASE_URL не задан -> миграция призов не требуется (локальный SQLite).')
        return
    src_db = os.path.join(BASE, 'prizes.db')
    if not os.path.exists(src_db):
        print('prizes.db не найден в проекте -> пропуск.')
        return
    conn = sqlite3.connect(src_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('SELECT * FROM prizes').fetchall()
    conn.close()
    pg = core._db()
    try:
        for r in rows:
            core._ex(pg, '''
                INSERT INTO prizes (account, game_id, level, reward_id, name, expiration_date,
                                    is_barcode, is_button, items, icon_ref, obtained_at,
                                    barcode, coupon_id, display_type)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ''', (r['account'], r['game_id'], r['level'], r['reward_id'], r['name'],
                  r['expiration_date'], r['is_barcode'], r['is_button'], r['items'],
                  r['icon_ref'], r['obtained_at'], r['barcode'], r['coupon_id'], r['display_type']))
        pg.commit()
        print(f'перенесено призов: {len(rows)}')
    finally:
        pg.close()


def copy_json():
    for fn in ('accounts.json', 'sessions.json', 'coupon_shares.json'):
        src = os.path.join(BASE, fn)
        dst = os.path.join(core.DATA_DIR, fn)
        if not os.path.exists(src):
            print(f'{fn}: нет локально ({src})')
            continue
        if os.path.abspath(src) == os.path.abspath(dst):
            print(f'{fn}: источник и назначение совпадают -> пропуск')
            continue
        if os.path.exists(dst):
            print(f'{fn}: уже есть в {core.DATA_DIR} -> пропуск')
            continue
        shutil.copy2(src, dst)
        print(f'{fn}: скопирован в {core.DATA_DIR}')


if __name__ == '__main__':
    migrate_prizes()
    copy_json()
