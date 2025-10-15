import argparse
import datetime as dt
import json
import logging
import random
import re
import time
from typing import Dict, List, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup
from pathlib import Path

from src.logger import set_logger
from settings import (
    CITY_NAME,
    AREA_MIN,
    AREA_MAX,
    HEADERS_POOL,
    OUTPUT_XLSX,
    OUTPUT_TAGGED_XLSX,
    WB_ZONES,
    WB_DISTANCE_THRESHOLD_M,
    COLUMN_ORDER,
    GEOCODER_UA,
    CITY_VIEWBOX,
)


log = logging.getLogger(__name__)
ITEM_RETRIES = 3


def parse_args():
    # Параметры командной строки
    parser = argparse.ArgumentParser(description="Simple scraper (Cian/Avito) + WB zones")
    parser.add_argument("--city", type=str, default="Москва", help="City name (default from settings)")
    parser.add_argument("--pages", type=int, default=1, help="Max pages per source")
    parser.add_argument("--wb-only", action="store_true", help="Only run WB checker for existing Excel")
    parser.add_argument("--no-avito", action="store_true", help="Skip Avito scraping")
    parser.add_argument("--no-cian", action="store_true", help="Skip Cian scraping")
    parser.add_argument("--legacy-wb", action="store_true", help="Use legacy wb_check_coordinates.py on Data/ads.xlsx")
    parser.add_argument("--geocode-missing", action="store_true", help="Geocode rows in Data/ads.xlsx with missing coords")
    parser.add_argument("--geocode-limit", type=int, default=50, help="Max rows to geocode per run")
    return parser.parse_args()


def _ua() -> Dict[str, str]:
    # Заголовки HTTP с реальным User‑Agent
    return {
        "User-Agent": random.choice(HEADERS_POOL),
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://google.com",
    }


def _sleep(a: float = 0.8, b: float = 2.2):
    # Случайная пауза между запросами
    time.sleep(random.uniform(a, b))


_geocode_cache: Dict[str, Dict[str, float]] = {}


def geocode_address(address: str, city: Optional[str] = None) -> Optional[Dict[str, float]]:
    # Геокодирование через Nominatim с ограничением по bbox города
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address, "format": "json", "limit": 1}
    if city:
        vb = CITY_VIEWBOX.get(city) or CITY_VIEWBOX.get(city.capitalize())
        if vb:
            left, top, right, bottom = vb
            params.update({
                "viewbox": f"{left},{top},{right},{bottom}",
                "bounded": 1,
            })
    headers = {"User-Agent": GEOCODER_UA}
    key = json.dumps({"q": address, "city": city, "vb": params.get("viewbox")}, ensure_ascii=False)
    if key in _geocode_cache:
        return _geocode_cache[key]
    last_error = None
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=25)
            resp.raise_for_status()
            data = resp.json()
            if data:
                result = {"lat": float(data[0]["lat"]), "lng": float(data[0]["lon"])}
                _geocode_cache[key] = result
                return result
            return None
        except Exception as e:
            last_error = e
            time.sleep(min(2 ** attempt, 6) + random.random())
    log.warning(f"Geocode failed for '{address}': {last_error}")
    return None


def normalize_address_for_geocoding(address: str, city: Optional[str]) -> str:
    # Очистка адреса для геокодера
    if not isinstance(address, str):
        return str(address)
    a = address.replace('На карте', '').strip(' ,')
    tokens_to_drop = [
        'р-н', 'район', 'АО', 'округ', 'адм. округ', 'АДМ Округ',
        'ЦАО', 'САО', 'СВАО', 'ЮВАО', 'ЮАО', 'ЮЗАО', 'ЗАО', 'СЗАО', 'НАО', 'ТАО', 'НАО (Новомосковский)', 'ТАО (Троицкий)'
    ]
    a = re.sub(r"\s*\([^\)]*\)", "", a)
    parts = [p.strip() for p in a.split(',') if p.strip()]
    filtered = [p for p in parts if not any(tok.lower() in p.lower() for tok in tokens_to_drop)]
    if city and all(city.lower() not in p.lower() for p in filtered):
        filtered.insert(0, city)
    return ', '.join(filtered) if filtered else (city + ', ' + a if city else a)


def normalize_url(url: str) -> str:
    # Нормализация ссылок для дедупликации
    try:
        from urllib.parse import urlparse, urlunparse
        s = str(url).strip()
        p = urlparse(s)
        scheme = p.scheme or 'https'
        netloc = (p.netloc or '').lower()
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        path = (p.path or '').rstrip('/')
        norm = urlunparse((scheme, netloc, path, '', '', ''))
        return norm
    except Exception:
        try:
            s = str(url)
            s = s.split('#', 1)[0].split('?', 1)[0].rstrip('/')
            s = s.replace('http://', 'https://')
            s = s.replace('https://www.', 'https://')
            return s
        except Exception:
            return url


def _now_iso() -> str:
    # Текущее время в ISO UTC
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _new_row() -> Dict:
    # Пустая строка под схему колонок
    return {k: None for k in COLUMN_ORDER}


def parse_area_m2_from_soup(text: str, soup: BeautifulSoup) -> Optional[float]:
    # Извлечение площади
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            jd = json.loads(script.string or "{}")
            if isinstance(jd, dict):
                fs = jd.get("floorSize") or {}
                if isinstance(fs, dict) and fs.get("value"):
                    return float(str(fs["value"]).replace(" ", "").replace("\u202f", "").replace(",", "."))
        except Exception:
            pass
    patterns = [
        r"(\d+[\s\u202f]?\d*[\.,]?\d*)\s*м²",
        r"Площад[ььи]\s*[:\-]?\s*(\d+[\s\u202f]?\d*[\.,]?\d*)",
        r"Общая\s+площад[ььи]\s*[:\-]?\s*(\d+[\s\u202f]?\d*[\.,]?\d*)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            try:
                return float(m.group(1).replace(" ", "").replace("\u202f", "").replace(",", "."))
            except Exception:
                continue
    return None


def scrape_cian(city: str, pages: int) -> List[Dict]:
    # Парсинг Циан (листинги + карточки)
    # Карта регионов для популярных городов
    CIAN_REGION_BY_CITY = {
        'москва': 1,
        'moscow': 1,
        'санкт-петербург': 2,
        'spb': 2,
    }
    records: List[Dict] = []
    session = requests.Session()
    empty_pages = 0  # подряд пустых страниц
    for p in range(1, pages + 1):
        try:
            url = "https://www.cian.ru/cat.php"
            params = {
                "deal_type": "rent",
                "engine_version": "2",
                "offer_type": "offices",
                "minarea": AREA_MIN,
                "maxarea": AREA_MAX,
                "region": CIAN_REGION_BY_CITY.get(city.lower(), 1),
                "p": p,
            }
            resp = session.get(url, params=params, headers=_ua(), timeout=30)
            if resp.status_code in (403, 429):
                log.info("Cian blocked page; skipping")
                break
            resp.raise_for_status()
            html = resp.text
            soup = BeautifulSoup(html, "lxml")
            links = []
            # Поиск ссылок на карточки
            for a in soup.select('a[data-name="LinkArea"], a[href]'):
                href = a.get("href")
                if not href:
                    continue
                if href.startswith("https://www.cian.ru/") and "/rent/" in href:
                    links.append(href.split("?", 1)[0])
            if not links:
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        jd = json.loads(script.string or "{}")
                        if isinstance(jd, dict) and jd.get("@type") == "ItemList":
                            items = jd.get("itemListElement") or []
                            for it in items:
                                url = None
                                if isinstance(it, dict):
                                    item = it.get("item") or {}
                                    if isinstance(item, dict):
                                        url = item.get("url") or item.get("@id")
                                if url and isinstance(url, str) and url.startswith("http"):
                                    if "/rent/" in url:
                                        links.append(url.split("?", 1)[0])
                    except Exception:
                        continue
            links = list(dict.fromkeys(links))
            if not links:
                log.info("Cian: no links on page %s", p)
                empty_pages += 1
                if empty_pages >= 3:
                    log.info("Cian: stop after 3 empty pages")
                    break
                continue
            empty_pages = 0
            log.info(f"Cian page {p}: found {len(links)} links")
            for link in links[:40]:
                _sleep()
                try:
                    resp_ok = None
                    for attempt in range(1, ITEM_RETRIES + 1):
                        r = session.get(link, headers=_ua(), timeout=30)
                        if r.status_code in (403, 429):
                            back = min(2 ** attempt, 8) + random.random()
                            time.sleep(back)
                            continue
                        try:
                            r.raise_for_status()
                            resp_ok = r
                            break
                        except Exception:
                            back = min(2 ** attempt, 8) + random.random()
                            time.sleep(back)
                    if not resp_ok:
                        continue
                    item_soup = BeautifulSoup(resp_ok.text, "lxml")
                    text = resp_ok.text
                    lat = lng = None
                    # Пытаемся извлечь координаты из JSON‑LD
                    for script in item_soup.find_all("script", type="application/ld+json"):
                        try:
                            jd = json.loads(script.string or "{}")
                            geo = jd.get("geo") or {}
                            if isinstance(geo, dict) and geo.get("latitude") and geo.get("longitude"):
                                lat = float(geo["latitude"])
                                lng = float(geo["longitude"])
                                break
                        except Exception:
                            continue
                    if lat is None or lng is None:
                        # Паттерн координат в тексте как запасной вариант
                        m = re.search(r'"latitude"\s*:\s*([0-9.]+).*?"longitude"\s*:\s*([0-9.]+)', text, re.S)
                        if m:
                            lat = float(m.group(1))
                            lng = float(m.group(2))

                    title = (item_soup.find("h1") or {}).get_text(strip=True) if item_soup.find("h1") else None
                    address = None
                    addr_node = item_soup.find("address")
                    if addr_node:
                        address = addr_node.get_text(" ", strip=True)
                    if not address:
                        # Поиск адреса в разметке
                        el = item_soup.find(attrs={"itemprop": "address"})
                        if el:
                            address = el.get_text(" ", strip=True)

                    area_m2 = parse_area_m2_from_soup(text, item_soup)

                    price_total = None
                    price_match = re.search(r"(\d+[\s\u202f]?\d+[\s\u202f]?\d*)\s*₽", text)
                    if price_match:
                        try:
                            price_total = float(price_match.group(1).replace(" ", "").replace("\u202f", ""))
                        except Exception:
                            price_total = None

                    if (area_m2 is not None) and (AREA_MIN <= area_m2 <= AREA_MAX):
                        if lat is None or lng is None:
                            if address:
                                search_addr = address
                                if city and isinstance(address, str) and city.lower() not in address.lower():
                                    search_addr = f"{city}, {address}"
                                geo = geocode_address(search_addr)
                                if geo:
                                    lat, lng = geo["lat"], geo["lng"]

                        row = _new_row()
                        row.update({
                            'source': 'cian',
                            'external_id': re.sub(r'\D', '', link) or None,
                            'url': normalize_url(link),
                            'title': title,
                            'address_raw': address,
                            'address_formatted': normalize_address_for_geocoding(address, city),
                            'city': city,
                            'lat': lat,
                            'lng': lng,
                            'area_m2': area_m2,
                            'price_total': price_total,
                            'price_per_m2': round(price_total/area_m2, 2) if price_total and area_m2 else None,
                            'last_seen_at': _now_iso(),
                            'status': 'active',
                        })
                        records.append(row)
                    else:
                        pass
                except Exception:
                    continue
        except Exception:
            break
    return records


def scrape_avito(city: str, pages: int) -> List[Dict]:
    # Парсинг Авито (листинги + карточки)
    records: List[Dict] = []
    session = requests.Session()
    AVITO_SLUG_BY_CITY = {
        'москва': 'moskva',
        'moscow': 'moskva',
        'санкт-петербург': 'sankt-peterburg',
        'спб': 'sankt-peterburg',
    }
    city_slug = AVITO_SLUG_BY_CITY.get(city.lower(), re.sub(r"\s+", "-", city.lower()))
    empty_pages = 0  # подряд пустых страниц
    for p in range(1, pages + 1):
        try:
            url = f"https://www.avito.ru/{city_slug}/kommercheskaya_nedvizhimost/sdam"
            params = {"p": p}
            resp = session.get(url, params=params, headers=_ua(), timeout=30)
            if resp.status_code in (403, 429):
                log.info("Avito blocked page; skipping")
                break
            resp.raise_for_status()
            html = resp.text
            soup = BeautifulSoup(html, "lxml")
            links = []
            # Поиск ссылок на карточки
            for a in soup.select('a[data-marker="item-title"]'):
                href = a.get("href")
                if not href:
                    continue
                href_full = href if href.startswith("http") else f"https://www.avito.ru{href}"
                links.append(href_full.split("?", 1)[0])
            if not links:
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    href_full = href if href.startswith("http") else f"https://www.avito.ru{href}"
                    if "/ad/" in href_full or "/id/" in href_full:
                        links.append(href_full.split("?", 1)[0])
            # Запасной вариант: window.__initialData__
            if not links:
                try:
                    m = re.search(r"window\.__initialData__\s*=\s*(\{.*?\})\s*;", html, re.S)
                    if m:
                        data = json.loads(m.group(1))
                        stack = [data]
                        while stack:
                            node = stack.pop()
                            if isinstance(node, dict):
                                if 'urlPath' in node and isinstance(node['urlPath'], str):
                                    u = node['urlPath']
                                    ufull = u if u.startswith('http') else f"https://www.avito.ru{u}"
                                    links.append(ufull.split('?', 1)[0])
                                for v in node.values():
                                    if isinstance(v, (dict, list)):
                                        stack.append(v)
                            elif isinstance(node, list):
                                stack.extend(node)
                except Exception:
                    pass
            links = list(dict.fromkeys(links))
            if not links:
                log.info("Avito: no links on page %s", p)
                empty_pages += 1
                if empty_pages >= 3:
                    log.info("Avito: stop after 3 empty pages")
                    break
                continue
            empty_pages = 0
            log.info(f"Avito page {p}: found {len(links)} links")
            for link in links[:40]:
                _sleep()
                try:
                    resp_ok = None
                    for attempt in range(1, ITEM_RETRIES + 1):
                        r = session.get(link, headers=_ua(), timeout=30)
                        if r.status_code in (403, 429):
                            back = min(2 ** attempt, 8) + random.random()
                            time.sleep(back)
                            continue
                        try:
                            r.raise_for_status()
                            resp_ok = r
                            break
                        except Exception:
                            back = min(2 ** attempt, 8) + random.random()
                            time.sleep(back)
                    if not resp_ok:
                        continue
                    text = resp_ok.text
                    item_soup = BeautifulSoup(text, "lxml")

                    # Координаты из data-map-state
                    lat = lng = None
                    m = re.search(r'data-map-state=\"(.*?)\"', text)
                    if m:
                        try:
                            state_json = json.loads(bytes(m.group(1), 'utf-8').decode('unicode_escape'))
                            points = state_json.get('points') or []
                            if points:
                                ll = points[0].get('ll') or []
                                if len(ll) == 2:
                                    lng, lat = float(ll[0]), float(ll[1])
                        except Exception:
                            pass

                    # Заголовок и адрес
                    title = item_soup.find('h1').get_text(strip=True) if item_soup.find('h1') else None
                    address = None
                    for label in item_soup.find_all(text=re.compile('Адрес')):
                        v = label.parent.find_next().get_text(" ", strip=True)
                        if v:
                            address = v
                            break
                    if not address:
                        el = item_soup.find(attrs={"itemprop": "address"})
                        if el:
                            address = el.get_text(" ", strip=True)

                    # Площадь
                    area_m2 = parse_area_m2_from_soup(text, item_soup)

                    price_total = None
                    price_match = re.search(r"(\d+[\s\u202f]?\d+[\s\u202f]?\d*)\s*₽", text)
                    if price_match:
                        try:
                            price_total = float(price_match.group(1).replace(" ", "").replace("\u202f", ""))
                        except Exception:
                            price_total = None

                    if (area_m2 is not None) and (AREA_MIN <= area_m2 <= AREA_MAX):
                        if lat is None or lng is None:
                            if address:
                                search_addr = address
                                if city and isinstance(address, str) and city.lower() not in address.lower():
                                    search_addr = f"{city}, {address}"
                                geo = geocode_address(search_addr)
                                if geo:
                                    lat, lng = geo["lat"], geo["lng"]

                        row = _new_row()
                        row.update({
                            'source': 'avito',
                            'external_id': re.sub(r'\D', '', link) or None,
                            'url': normalize_url(link),
                            'title': title,
                            'address_raw': address,
                            'address_formatted': normalize_address_for_geocoding(address, city),
                            'city': city,
                            'lat': lat,
                            'lng': lng,
                            'area_m2': area_m2,
                            'price_total': price_total,
                            'price_per_m2': round(price_total/area_m2, 2) if price_total and area_m2 else None,
                            'last_seen_at': _now_iso(),
                            'status': 'active',
                        })
                        records.append(row)
                except Exception:
                    continue
        except Exception:
            break
    return records


def _ensure_coords_and_notes(df: pd.DataFrame, geocode_limit: Optional[int] = None) -> int:
    # Заполнение координат и строки notes для чекера
    updated = 0
    if df.empty:
        return updated
    for idx, row in df.iterrows():
        lat = row.get('lat')
        lng = row.get('lng')
        if pd.notna(lat) and pd.notna(lng):
            note = row.get('notes')
            legacy = f"lat = {lat}, lng = {lng}"
            if not isinstance(note, str) or 'lat =' not in note:
                df.at[idx, 'notes'] = legacy
            continue
        if geocode_limit is not None and updated >= geocode_limit:
            continue
        address = normalize_address_for_geocoding(row.get('address_raw') or row.get('title'), row.get('city'))
        if not address:
            continue
        geo = geocode_address(str(address), city=row.get('city'))
        if not geo:
            continue
        df.at[idx, 'lat'] = geo['lat']
        df.at[idx, 'lng'] = geo['lng']
        df.at[idx, 'notes'] = f"lat = {geo['lat']}, lng = {geo['lng']}"
        updated += 1
        _sleep(0.6, 1.5)
    return updated


def save_and_check(records: List[Dict], use_legacy_wb: bool = False, geocode_limit: Optional[int] = 100):
    # Сохранение Excel, дедупликация, автогеокодинг, запуск чекера WB
    Path('Data').mkdir(exist_ok=True)
    df = pd.DataFrame(records, columns=COLUMN_ORDER)
    if not df.empty:
        if 'url' in df.columns:
            try:
                df['url'] = df['url'].map(normalize_url)
            except Exception:
                pass
        before = len(df)
        keys = []
        if 'source' in df.columns and 'external_id' in df.columns:
            keys.append(['source','external_id'])
        if 'url' in df.columns:
            keys.append(['url'])
        seen = set()
        keep_rows = []
        for _, r in df.iterrows():
            dedup_key = []
            for k in keys:
                dedup_key.append(tuple((kname, r.get(kname)) for kname in k))
            dedup_key = tuple(dedup_key)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            keep_rows.append(r)
        df = pd.DataFrame(keep_rows, columns=COLUMN_ORDER)
        after = len(df)
        if after != before:
            log.info(f"Deduplicated rows: {before} -> {after}")
    geocoded = _ensure_coords_and_notes(df, geocode_limit=geocode_limit)
    if geocoded:
        log.info(f"Auto-geocoded (save step) rows: {geocoded}")
    try:
        if 'address_formatted' in df.columns:
            df['address_formatted'] = [
                normalize_address_for_geocoding(r.get('address_raw') or r.get('title'), r.get('city'))
                for _, r in df.iterrows()
            ]
    except Exception:
        pass
    df.to_excel(OUTPUT_XLSX, index=False)
    try:
        import subprocess, sys
        cmd = [sys.executable, 'wb_check_coordinates.py']
        log.info("Running legacy WB checker via subprocess ...")
        subprocess.run(cmd, check=True)
    except Exception as e:
        log.error(f"Legacy WB checker failed: {e}")


def geocode_missing_in_xlsx(limit: int = 50, run_legacy: bool = False):
    # Догеокодировать пропуски в существующем Excel
    Path('Data').mkdir(exist_ok=True)
    try:
        df = pd.read_excel(OUTPUT_XLSX)
    except Exception as e:
        log.error(f"Cannot read {OUTPUT_XLSX}: {e}")
        return

    if df.empty:
        log.info("DataFrame is empty, nothing to geocode")
        return

    updated = 0
    for idx, row in df.iterrows():
        if updated >= limit:
            break
        lat = row.get('lat')
        lng = row.get('lng')
        if pd.notna(lat) and pd.notna(lng):
            continue
        address = normalize_address_for_geocoding(row.get('address_raw') or row.get('title') or row.get('url'), row.get('city'))
        if not address:
            continue
        geo = geocode_address(str(address), city=row.get('city'))
        if not geo:
            continue
        df.at[idx, 'lat'] = geo['lat']
        df.at[idx, 'lng'] = geo['lng']
        df.at[idx, 'notes'] = f"lat = {geo['lat']}, lng = {geo['lng']}"
        updated += 1
        _sleep(0.6, 1.5)

    df.to_excel(OUTPUT_XLSX, index=False)
    log.info(f"Geocoded rows updated: {updated}")
    if run_legacy:
        try:
            import subprocess, sys
            subprocess.run([sys.executable, 'wb_check_coordinates.py'], check=True)
        except Exception as e:
            log.error(f"Legacy WB checker failed: {e}")


def main():
    set_logger()
    args = parse_args()
    city = args.city or CITY_NAME
    if args.wb_only:
        logging.info("WB-only mode: tagging zones for existing Excel")
        try:
            import subprocess, sys
            subprocess.run([sys.executable, 'wb_check_coordinates.py'], check=True)
        except Exception as e:
            log.error(f"Legacy WB checker failed: {e}")
        return

    if args.geocode_missing:
        logging.info("Geocoding missing coordinates in existing Excel ...")
        geocode_missing_in_xlsx(limit=args.geocode_limit, run_legacy=args.legacy_wb)
        return

    all_records: List[Dict] = []
    if not args.no_cian:
        logging.info("Scraping Cian ...")
        all_records.extend(scrape_cian(city, args.pages))
    if not args.no_avito:
        logging.info("Scraping Avito ...")
        all_records.extend(scrape_avito(city, args.pages))

    logging.info(f"Collected records: {len(all_records)}")
    save_and_check(all_records, use_legacy_wb=args.legacy_wb, geocode_limit=None)


if __name__ == "__main__":
    main()


