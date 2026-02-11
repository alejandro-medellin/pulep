"""Utilidades para extraer información pública del módulo de Eventos de PULEP."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Dict, List, Tuple
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://pulepapp.mincultura.gov.co"
EVENTS_PATH = "/InformesPublicos/Eventos"
EVENTS_GRID_PATH = "/InformesPublicos/ObtenerEventos"
EVENT_DETAIL_PATH = "/InformesPublicos/EventoFichap/{evento_id}"


@dataclass
class ScraperConfig:
    timeout: int = 40
    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0 Safari/537.36"
    )


def _make_session(config: ScraperConfig | None = None) -> requests.Session:
    cfg = config or ScraperConfig()
    session = requests.Session()
    session.headers.update({"User-Agent": cfg.user_agent})
    return session


def _get_events_page(session: requests.Session, params: Dict[str, str] | None = None) -> str:
    response = session.get(
        urljoin(BASE_URL, EVENTS_PATH),
        params=params,
        timeout=ScraperConfig().timeout,
    )
    response.raise_for_status()
    return response.text


def _fetch_events_grid_page(
    session: requests.Session,
    filters: Dict[str, str],
    page: int,
    rows: int,
) -> Dict[str, object]:
    """Obtiene una página JSON del grid de eventos (jqGrid)."""
    # El backend aplica filtros a partir del request GET previo al módulo de eventos.
    session.get(urljoin(BASE_URL, EVENTS_PATH), params=filters, timeout=ScraperConfig().timeout).raise_for_status()

    payload = {
        "_search": "false",
        "nd": "0",
        "rows": str(rows),
        "page": str(page),
        "sidx": "",
        "sord": "asc",
    }
    response = session.post(
        urljoin(BASE_URL, EVENTS_GRID_PATH),
        data=payload,
        timeout=ScraperConfig().timeout,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Respuesta inesperada del endpoint de eventos")
    return data


def _build_detail_url(evento_id: object) -> str:
    if evento_id is None:
        return ""
    return urljoin(BASE_URL, EVENT_DETAIL_PATH.format(evento_id=evento_id))


def extract_filter_options(html: str) -> Dict[str, Dict[str, str]]:
    """Devuelve las opciones de todos los select del formulario de filtros."""
    soup = BeautifulSoup(html, "html.parser")
    filters: Dict[str, Dict[str, str]] = {}

    form = soup.find("form")
    if not form:
        return filters

    for select in form.find_all("select"):
        name = select.get("name") or select.get("id")
        if not name:
            continue
        options: Dict[str, str] = {}
        for option in select.find_all("option"):
            value = (option.get("value") or "").strip()
            label = option.get_text(strip=True)
            if value or label:
                options[label or value] = value
        filters[name] = options

    return filters


def _find_results_table(soup: BeautifulSoup):
    tables = soup.find_all("table")
    if not tables:
        return None

    for table in tables:
        headers = [h.get_text(" ", strip=True).lower() for h in table.find_all("th")]
        if any("evento" in h for h in headers):
            return table

    return tables[0]


def parse_events_table(html: str) -> pd.DataFrame:
    """Parsea la tabla de resultados de eventos y devuelve un DataFrame."""
    soup = BeautifulSoup(html, "html.parser")
    table = _find_results_table(soup)
    if table is None:
        return pd.DataFrame()

    header_cells = table.find("thead")
    headers = [
        th.get_text(" ", strip=True)
        for th in (header_cells.find_all("th") if header_cells else table.find_all("th"))
    ]

    body = table.find("tbody") or table
    rows = []
    for tr in body.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        row = [c.get_text(" ", strip=True) for c in cells]

        detail_link = tr.find("a", href=True)
        row_dict = {headers[idx] if idx < len(headers) else f"col_{idx+1}": value for idx, value in enumerate(row)}
        row_dict["detalle_url"] = urljoin(BASE_URL, detail_link["href"]) if detail_link else ""
        rows.append(row_dict)

    return pd.DataFrame(rows)


def parse_event_detail(html: str) -> Dict[str, str]:
    """Parsea una página de detalle y devuelve pares campo/valor."""
    soup = BeautifulSoup(html, "html.parser")
    data: Dict[str, str] = {}

    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) >= 2:
                key = cells[0].get_text(" ", strip=True)
                value = cells[1].get_text(" ", strip=True)
                if key:
                    data[key] = value

    for label in soup.find_all(["label", "strong", "b"]):
        key = label.get_text(" ", strip=True).rstrip(":")
        if not key:
            continue
        sibling_text = ""
        next_node = label.next_sibling
        if next_node:
            sibling_text = str(next_node).strip()
        if sibling_text and key not in data:
            data[key] = BeautifulSoup(sibling_text, "html.parser").get_text(" ", strip=True)

    if not data:
        data["contenido"] = soup.get_text(" ", strip=True)

    return data


def scrape_events(
    filters: Dict[str, str],
    include_details: bool = True,
    max_details: int | None = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    session = _make_session()
    try:
        first_page = _fetch_events_grid_page(session, filters=filters, page=1, rows=100)

        total_pages = int(first_page.get("total") or 0)
        rows_data = list(first_page.get("rows") or [])

        for current_page in range(2, total_pages + 1):
            page_data = _fetch_events_grid_page(session, filters=filters, page=current_page, rows=100)
            rows_data.extend(page_data.get("rows") or [])

        basic_df = pd.DataFrame(rows_data)
        if not basic_df.empty and "EventoId" in basic_df.columns:
            basic_df["detalle_url"] = basic_df["EventoId"].map(_build_detail_url)
        elif "detalle_url" not in basic_df.columns:
            basic_df["detalle_url"] = ""
    except (requests.RequestException, ValueError):
        # Fallback conservador: parseo directo de una tabla HTML si existe.
        html = _get_events_page(session, params=filters)
        basic_df = parse_events_table(html)

    if not include_details or basic_df.empty:
        return basic_df, pd.DataFrame()

    detail_rows: List[Dict[str, str]] = []
    links = [u for u in basic_df.get("detalle_url", pd.Series(dtype=str)).tolist() if u]
    if max_details is not None:
        links = links[:max_details]

    for idx, url in enumerate(links, start=1):
        try:
            response = session.get(url, timeout=ScraperConfig().timeout)
            response.raise_for_status()
            detail = parse_event_detail(response.text)
            detail["detalle_url"] = url
            detail["indice"] = str(idx)
            detail_rows.append(detail)
        except requests.RequestException as exc:
            detail_rows.append({"detalle_url": url, "error": str(exc), "indice": str(idx)})

    return basic_df, pd.DataFrame(detail_rows)


def dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name: str) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name[:31] or "datos")
    output.seek(0)
    return output.getvalue()


def normalize_filter_values(raw_values: Dict[str, object]) -> Dict[str, str]:
    cleaned: Dict[str, str] = {}
    for key, value in raw_values.items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
            cleaned[key] = value
            continue
        cleaned[key] = str(value)
    return cleaned
