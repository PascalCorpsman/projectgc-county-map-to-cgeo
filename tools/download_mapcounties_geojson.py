#!/usr/bin/env python3
"""Download county map data from Project-GC and export as GeoJSON.

This script reuses the Firefox-cookie based authentication flow used in the
CreateLists tooling. It opens the target MapCounties page and tries to extract
county geometry/color data as a GeoJSON FeatureCollection.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
import tempfile
import webbrowser
from html import unescape
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import quote, unquote_plus, urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener


DEFAULT_URL_TEMPLATE = (
    "https://project-gc.com/Maps/MapCounties"
    "?pre_pr_profileName={username}"
    "&pre_crc_country={country}"
    "&post_crc_country={country}"
    "&submit=Filter"
)

DEFAULT_CONFIG_PATH = str((Path(__file__).resolve().parent.parent / "config.json").resolve())


def fetch_url(opener, url: str, data: Optional[bytes] = None, extra_headers: Optional[Dict[str, str]] = None) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/127.0",
        "Accept-Language": "de,en-US;q=0.7,en;q=0.3",
    }
    if extra_headers:
        headers.update(extra_headers)

    req = Request(url, data=data, headers=headers)
    with opener.open(req, timeout=40) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_username(config: Dict[str, object]) -> str:
    for key in ("profilename", "profileName", "username", "user", "name"):
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError("Kein gueltiger Benutzername in config.json gefunden.")


def resolve_country(config: Dict[str, object]) -> str:
    for key in ("country", "Country", "land"):
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Germany"


def resolve_use_firefox_cookies(config: Dict[str, object]) -> bool:
    value = config.get("AutoUseFirefoxCookies", True)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "ja", "on"}
    return bool(value)


def resolve_interactive_browser_login(config: Dict[str, object]) -> bool:
    value = config.get("InteractiveBrowserLogin", True)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "ja", "on"}
    return bool(value)


def resolve_cookie_header(config: Dict[str, object]) -> str:
    for key in ("projectgc_cookie", "cookie", "cookies"):
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _candidate_firefox_cookie_dbs(config: Dict[str, object]) -> List[Path]:
    configured = config.get("FirefoxProfilePath")
    candidates: List[Path] = []

    if isinstance(configured, str) and configured.strip():
        custom = Path(configured).expanduser()
        candidates.append(custom / "cookies.sqlite")

    base = Path.home() / ".mozilla" / "firefox"
    if base.is_dir():
        for p in sorted(base.glob("*.default*")):
            candidates.append(p / "cookies.sqlite")

    unique: List[Path] = []
    seen: Set[str] = set()
    for p in candidates:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def _read_projectgc_cookie_header_from_sqlite(db_path: Path) -> str:
    if not db_path.is_file():
        return ""

    with tempfile.TemporaryDirectory(prefix="pgc-cookie-") as tmp:
        tmp_db = Path(tmp) / "cookies.sqlite"
        shutil.copy2(db_path, tmp_db)

        conn = sqlite3.connect(str(tmp_db))
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT name, value
                FROM moz_cookies
                WHERE host LIKE '%project-gc.com%'
                ORDER BY lastAccessed DESC
                """
            )
            rows = cur.fetchall()
        finally:
            conn.close()

    if not rows:
        return ""

    cookie_map: Dict[str, str] = {}
    for name, value in rows:
        if not name:
            continue
        key = str(name)
        if key in cookie_map:
            continue
        cookie_map[key] = str(value)

    if not cookie_map:
        return ""

    return "; ".join(f"{k}={v}" for k, v in cookie_map.items())


def resolve_cookie_header_from_firefox(config: Dict[str, object]) -> str:
    for db_path in _candidate_firefox_cookie_dbs(config):
        try:
            header = _read_projectgc_cookie_header_from_sqlite(db_path)
        except Exception:
            continue
        if header:
            return header
    return ""


def _extract_script_blocks(html: str) -> Tuple[List[str], List[str]]:
    inline_blocks: List[str] = []
    src_urls: List[str] = []

    for match in re.finditer(r"<script\b([^>]*)>(.*?)</script>", html, flags=re.IGNORECASE | re.DOTALL):
        attrs = match.group(1)
        body = match.group(2)
        src_match = re.search(r"src\s*=\s*['\"]([^'\"]+)['\"]", attrs, flags=re.IGNORECASE)
        if src_match:
            src_urls.append(unescape(src_match.group(1)))
        if body and body.strip():
            inline_blocks.append(body)

    return inline_blocks, src_urls


def _find_enclosing_json_object(text: str, pos: int) -> Optional[str]:
    start = text.rfind("{", 0, pos + 1)
    while start >= 0:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    if i >= pos:
                        return text[start : i + 1]
                    break
        start = text.rfind("{", 0, start)

    return None


def _iter_candidate_json_strings(text: str) -> Iterable[str]:
    for marker in ("\"FeatureCollection\"", "\"features\"", "\"coordinates\""):
        idx = 0
        while True:
            idx = text.find(marker, idx)
            if idx < 0:
                break
            candidate = _find_enclosing_json_object(text, idx)
            if candidate:
                yield candidate
            idx += len(marker)


# Try to find FeatureCollection objects recursively in potentially nested payloads.
def _find_feature_collection_in_object(obj):
    if isinstance(obj, dict):
        if obj.get("type") == "FeatureCollection" and isinstance(obj.get("features"), list):
            return obj
        for value in obj.values():
            found = _find_feature_collection_in_object(value)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_feature_collection_in_object(item)
            if found is not None:
                return found
    return None


def _extract_candidate_endpoints(text: str) -> List[str]:
    candidates: List[str] = []

    patterns = [
        r"['\"](/ajax/[^'\"\s]+)['\"]",
        r"['\"](/Maps/[^'\"\s]+)['\"]",
        r"['\"]([^'\"\s]+\.geojson(?:\?[^'\"\s]*)?)['\"]",
        r"['\"](/api/[^'\"\s]+)['\"]",
    ]

    for pattern in patterns:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            val = unescape(m.group(1))
            if len(val) > 4:
                candidates.append(val)

    # keep order, drop duplicates
    deduped: List[str] = []
    seen: Set[str] = set()
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        deduped.append(c)
    return deduped


def _normalize_color(value: str) -> str:
    value = value.strip()
    if re.match(r"^#[0-9A-Fa-f]{6}$", value):
        return value.lower()

    named = {
        "red": "#ff3333",
        "green": "#116611",
        "yellow": "#f0c20f",
        "orange": "#ff9900",
        "blue": "#3366cc",
        "gray": "#808080",
        "grey": "#808080",
    }
    return named.get(value.lower(), "#f0c20f")


def _extract_leaflet_polygons(html: str) -> List[Dict[str, object]]:
    features: List[Dict[str, object]] = []
    token = "new L.geoJson(JSON.parse('"
    pos = 0

    while True:
        start = html.find(token, pos)
        if start < 0:
            break

        geom_start = start + len(token)
        geom_end = html.find("'), {", geom_start)
        if geom_end < 0:
            pos = start + len(token)
            continue

        style_start = geom_end + len("'), {")
        add_to_map = html.find("}).addTo(map);", style_start)
        if add_to_map < 0:
            pos = start + len(token)
            continue

        popup_start = html.find("bindPopup('", add_to_map)
        popup_end = -1
        popup_text = ""
        if popup_start >= 0:
            popup_content_start = popup_start + len("bindPopup('")
            popup_end = html.find("');", popup_content_start)
            if popup_end > popup_content_start:
                popup_text = html[popup_content_start:popup_end]

        geom_text = html[geom_start:geom_end]
        style_text = html[style_start:add_to_map]

        try:
            geometry = json.loads(geom_text)
        except Exception:
            pos = add_to_map + 1
            continue

        color_match = re.search(r"fillColor\s*:\s*'([^']+)'", style_text)
        if not color_match:
            color_match = re.search(r"color\s*:\s*'([^']+)'", style_text)
        fill = _normalize_color(color_match.group(1) if color_match else "")

        fill_opacity_match = re.search(r"fillOpacity\s*:\s*([0-9.]+)", style_text)
        stroke_opacity_match = re.search(r"opacity\s*:\s*([0-9.]+)", style_text)
        weight_match = re.search(r"weight\s*:\s*([0-9.]+)", style_text)

        county = ""
        county_qs = re.search(r"post_crc_county=([^&'\"]+)", popup_text)
        if county_qs:
            county = unquote_plus(county_qs.group(1)).strip()
        if not county:
            county_label = re.search(r" in ([^<]+)<br>", popup_text)
            if county_label:
                county = unescape(county_label.group(1)).strip()
        if not county:
            county = f"County {len(features) + 1}"

        features.append(
            {
                "id": f"feature_{len(features):03d}",
                "type": "Feature",
                "properties": {
                    "GEN": county,
                    "stroke-opacity": float(stroke_opacity_match.group(1)) if stroke_opacity_match else 0.6,
                    "stroke-widt": int(float(weight_match.group(1))) if weight_match else 2,
                    "fill-opacity": float(fill_opacity_match.group(1)) if fill_opacity_match else 0.2,
                    "fill": fill,
                    "stroke": fill,
                },
                "geometry": geometry,
            }
        )

        pos = (popup_end + 3) if popup_end > 0 else (add_to_map + 1)

    return features


def _normalize_feature_collection(collection: Dict[str, object]) -> Dict[str, object]:
    features_in = collection.get("features")
    if not isinstance(features_in, list):
        raise ValueError("FeatureCollection enthaelt kein gueltiges 'features'-Array.")

    out_features: List[Dict[str, object]] = []
    for idx, feature in enumerate(features_in):
        if not isinstance(feature, dict):
            continue

        geometry = feature.get("geometry")
        if not isinstance(geometry, dict):
            continue

        properties = feature.get("properties")
        if not isinstance(properties, dict):
            properties = {}

        gen = properties.get("GEN")
        if not isinstance(gen, str) or not gen.strip():
            for key in ("name", "county", "County", "county_name", "label"):
                value = properties.get(key)
                if isinstance(value, str) and value.strip():
                    gen = value.strip()
                    break
        if not isinstance(gen, str) or not gen.strip():
            gen = f"County {idx + 1}"

        fill = properties.get("fill")
        if not isinstance(fill, str) or not re.match(r"^#[0-9A-Fa-f]{6}$", fill):
            for key in ("color", "colour", "stroke"):
                value = properties.get(key)
                if isinstance(value, str) and re.match(r"^#[0-9A-Fa-f]{6}$", value):
                    fill = value
                    break
        if not isinstance(fill, str):
            fill = "#f0c20f"

        new_properties = dict(properties)
        new_properties["GEN"] = gen
        new_properties["stroke-opacity"] = float(new_properties.get("stroke-opacity", 0.6))
        new_properties["stroke-widt"] = int(new_properties.get("stroke-widt", 2))
        new_properties["fill-opacity"] = float(new_properties.get("fill-opacity", 0.2))
        new_properties["fill"] = fill
        new_properties["stroke"] = fill

        out_features.append(
            {
                "id": feature.get("id") or f"feature_{idx:03d}",
                "type": "Feature",
                "properties": new_properties,
                "geometry": geometry,
            }
        )

    return {
        "type": "FeatureCollection",
        "features": out_features,
    }


def extract_feature_collection(opener, map_url: str, html: str, extra_headers: Dict[str, str]) -> Dict[str, object]:
    # 0) MapCounties often injects one polygon at a time via Leaflet JS.
    leaflet_features = _extract_leaflet_polygons(html)
    if leaflet_features:
        return {
            "type": "FeatureCollection",
            "features": leaflet_features,
        }

    # 1) Directly embedded JSON in HTML.
    for candidate in _iter_candidate_json_strings(html):
        try:
            obj = json.loads(candidate)
        except Exception:
            continue
        found = _find_feature_collection_in_object(obj)
        if isinstance(found, dict):
            return found

    # 2) Search inline scripts and referenced scripts for endpoint hints.
    inline_scripts, src_urls = _extract_script_blocks(html)
    script_text = "\n".join(inline_scripts)

    endpoint_candidates = _extract_candidate_endpoints(script_text)

    # Pull external scripts and collect additional endpoint patterns.
    for src in src_urls:
        src_abs = urljoin(map_url, src)
        if not src_abs.startswith("https://project-gc.com"):
            continue
        try:
            src_body = fetch_url(opener, src_abs, extra_headers=extra_headers)
        except Exception:
            continue

        for candidate in _iter_candidate_json_strings(src_body):
            try:
                obj = json.loads(candidate)
            except Exception:
                continue
            found = _find_feature_collection_in_object(obj)
            if isinstance(found, dict):
                return found

        endpoint_candidates.extend(_extract_candidate_endpoints(src_body))

    # 3) Try candidate JSON endpoints.
    seen_urls: Set[str] = set()
    for endpoint in endpoint_candidates:
        target = urljoin(map_url, endpoint)
        if target in seen_urls:
            continue
        seen_urls.add(target)

        if "project-gc.com" not in target:
            continue

        try:
            body = fetch_url(opener, target, extra_headers=extra_headers)
        except Exception:
            continue

        # JSON endpoint
        try:
            obj = json.loads(body)
            found = _find_feature_collection_in_object(obj)
            if isinstance(found, dict):
                return found
        except Exception:
            pass

        # Sometimes endpoint returns JS containing JSON.
        for candidate in _iter_candidate_json_strings(body):
            try:
                obj = json.loads(candidate)
            except Exception:
                continue
            found = _find_feature_collection_in_object(obj)
            if isinstance(found, dict):
                return found

    raise RuntimeError(
        "Konnte kein FeatureCollection-Objekt auf der MapCounties-Seite finden. "
        "Moeglicherweise fehlt Login/Premium oder die Seite hat das Datenformat geaendert."
    )


def build_map_url(username: str, country: str) -> str:
    return DEFAULT_URL_TEMPLATE.format(username=quote(username), country=quote(country))


def save_geojson(path: Path, feature_collection: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(feature_collection, f, ensure_ascii=False, separators=(",", ":"))


def normalize_user_path(raw_path: str) -> Path:
    # Accept both slash styles in console input, e.g. ../file.json and ..\file.json.
    normalized = raw_path.strip().replace("\\", "/")
    path = Path(normalized).expanduser()
    if not path.suffix:
        path = path.with_suffix(".geojson")
    return path


def prompt_output_path(default_output: str) -> Path:
    default_path = normalize_user_path(default_output)
    if not sys.stdin.isatty():
        return default_path

    value = input(f"Dateiname fuer Export [Enter = {default_path}]: ").strip()
    if not value:
        return default_path
    return normalize_user_path(value)


def looks_like_http_url(value: str) -> bool:
    lower = value.strip().lower()
    return lower.startswith("http://") or lower.startswith("https://")


def main() -> int:
    parser = argparse.ArgumentParser(description="Laedt Project-GC MapCounties als GeoJSON herunter.")
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Pfad zur Konfiguration (Default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--country",
        default="",
        help="Optional: Land direkt setzen (ueberschreibt config)",
    )
    parser.add_argument(
        "--output",
        default="test.geojson",
        help="Standard-Ausgabedatei fuer den Prompt (Default: test.geojson)",
    )
    parser.add_argument(
        "--username",
        default="",
        help="Optional: Profilname direkt setzen (ueberschreibt config)",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_file():
        raise FileNotFoundError(f"Config-Datei nicht gefunden: {config_path}")

    config = load_json(config_path)
    if not isinstance(config, dict):
        raise ValueError("Config muss ein JSON-Objekt sein.")

    username = args.username.strip() if args.username.strip() else resolve_username(config)
    country = args.country.strip() if args.country.strip() else resolve_country(config)
    use_firefox_cookies = resolve_use_firefox_cookies(config)
    interactive_browser_login = resolve_interactive_browser_login(config)

    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    output_path_override: Optional[Path] = None

    cookie_header = resolve_cookie_header(config)
    if not cookie_header and use_firefox_cookies:
        cookie_header = resolve_cookie_header_from_firefox(config)
        if cookie_header:
            print("Info: Project-GC Cookie aus Firefox-Profil geladen.")

    map_url = build_map_url(username=username, country=country)

    if interactive_browser_login and sys.stdin.isatty():
        print("Info: Oeffne Firefox fuer Login und Kartenansicht...")
        try:
            webbrowser.open(map_url, new=2)
        except Exception:
            pass
        input(
            "Bitte Karte in Firefox einstellen (Filter/Land/Profil), "
            "danach hier Enter druecken..."
        )

        browser_url = input(
            "Kopiere die aktuelle Map-URL aus deinem Browser (Adressleiste) "
            f"und gib sie hier ein [Enter = Default {country}/{username}]: "
        ).strip()
        if browser_url:
            if looks_like_http_url(browser_url):
                map_url = browser_url
                print(f"Info: Verwende Map-URL aus Browser: {map_url}")
            else:
                # Falls User ausversehen einen Dateinamen eingab
                output_path_override = normalize_user_path(browser_url)
                print(f"Info: Das sieht nach einem Dateinamen aus, wird direkt verwendet: {output_path_override}")

        if use_firefox_cookies:
            updated_cookie = resolve_cookie_header_from_firefox(config)
            if updated_cookie:
                cookie_header = updated_cookie
                print("Info: Project-GC Cookie nach Browser-Session aktualisiert.")
    elif interactive_browser_login and not sys.stdin.isatty():
        print(
            "Warnung: Kein interaktives Terminal, Browser-Interaktion wird uebersprungen.",
            file=sys.stderr,
        )

    if not cookie_header:
        print(
            "Warnung: Es wurde kein Cookie gefunden. Es wird ohne Cookie versucht (wahrscheinlich unzureichend).",
            file=sys.stderr,
        )

    headers = {"Cookie": cookie_header} if cookie_header else {}

    print(f"Info: Lade MapCounties fuer Profil '{username}' und Land '{country}'...")
    html = fetch_url(opener, map_url, extra_headers=headers)

    if "Not logged in" in html and "Authenticate" in html:
        raise PermissionError("Project-GC meldet 'Not logged in'. Bitte erneut in Firefox anmelden.")

    if "Membership required" in html or "title=\"Membership required\"" in html:
        print(
            "Warnung: Seite zeigt Membership-Hinweise. Download kann dadurch fehlschlagen.",
            file=sys.stderr,
        )

    raw_collection = extract_feature_collection(opener, map_url, html, headers)
    normalized = _normalize_feature_collection(raw_collection)

    if output_path_override is not None:
        output_path = output_path_override
    else:
        output_path = prompt_output_path(args.output)
    save_geojson(output_path, normalized)
    print(f"OK: {len(normalized['features'])} Features nach '{output_path}' geschrieben.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        raise SystemExit(2)
