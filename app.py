from __future__ import annotations

import streamlit as st

from scraper import (
    _get_events_page,
    _make_session,
    dataframe_to_excel_bytes,
    extract_filter_options,
    normalize_filter_values,
    scrape_events,
)

st.set_page_config(page_title="Scraper PULEP Eventos", layout="wide")
st.title("Scraper PULEP - Consulta de Eventos")
st.caption(
    "Selecciona filtros equivalentes a la página oficial y descarga dos archivos Excel "
    "(resumen y detalle)."
)

if "filter_options" not in st.session_state:
    with st.spinner("Cargando filtros disponibles desde PULEP..."):
        try:
            html = _get_events_page(_make_session())
            st.session_state.filter_options = extract_filter_options(html)
        except Exception as exc:  # noqa: BLE001
            st.session_state.filter_options = {}
            st.error(f"No fue posible cargar filtros automáticamente: {exc}")

options = st.session_state.get("filter_options", {})

st.subheader("1) Filtros")
with st.form("filters_form"):
    selected = {}

    if options:
        cols = st.columns(2)
        for idx, (field_name, field_options) in enumerate(options.items()):
            labels = ["(Todos)"] + list(field_options.keys())
            selected_label = cols[idx % 2].selectbox(
                label=field_name,
                options=labels,
                index=0,
                key=f"sel_{field_name}",
            )
            if selected_label != "(Todos)":
                selected[field_name] = field_options[selected_label]
    else:
        st.info(
            "No se detectaron selectores automáticos. Puedes enviar filtros manuales "
            "en formato clave=valor, separados por comas."
        )
        manual = st.text_input("Filtros manuales", placeholder="anio=2025,departamento=11")
        if manual.strip():
            for pair in manual.split(","):
                if "=" in pair:
                    key, value = pair.split("=", maxsplit=1)
                    selected[key.strip()] = value.strip()

    include_detail = st.checkbox("Extraer también el detalle de cada evento", value=True)
    max_details = st.number_input(
        "Máximo de eventos para detalle (0 = todos)",
        min_value=0,
        value=100,
        step=10,
    )

    submitted = st.form_submit_button("Consultar y procesar")

st.subheader("2) Resultado")
if submitted:
    filtros = normalize_filter_values(selected)
    detail_limit = None if max_details == 0 else int(max_details)

    with st.spinner("Extrayendo información de eventos..."):
        try:
            basic_df, detail_df = scrape_events(
                filters=filtros,
                include_details=include_detail,
                max_details=detail_limit,
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"No fue posible completar la extracción: {exc}")
            st.stop()

    st.success(f"Consulta finalizada. Registros base: {len(basic_df)} | Detalles: {len(detail_df)}")

    tab1, tab2 = st.tabs(["Información básica", "Información detallada"])

    with tab1:
        st.dataframe(basic_df, use_container_width=True)
        st.download_button(
            "Descargar Excel de información básica",
            data=dataframe_to_excel_bytes(basic_df, "eventos_resumen"),
            file_name="pulep_eventos_resumen.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with tab2:
        st.dataframe(detail_df, use_container_width=True)
        st.download_button(
            "Descargar Excel de información detallada",
            data=dataframe_to_excel_bytes(detail_df, "eventos_detalle"),
            file_name="pulep_eventos_detalle.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

st.markdown("---")
st.caption(
    "Nota: este scraper depende de la estructura HTML pública del PULEP. "
    "Si la entidad cambia la web, puede requerir ajustes en el parser."
)
