# Scraper PULEP (Eventos) con Streamlit

Aplicación web para consultar el módulo público de eventos del PULEP y exportar resultados en dos archivos Excel:

1. **Información básica** de eventos (tabla principal).
2. **Información detallada** de cada evento (desde el enlace "Ver evento").

## Requisitos

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Ejecución

```bash
streamlit run app.py
```

## Flujo funcional

- La app intenta cargar automáticamente los filtros (`select`) disponibles en la página de eventos de PULEP.
- El usuario selecciona filtros equivalentes y ejecuta la consulta.
- El scraper obtiene:
  - tabla de resultados (nivel básico),
  - detalle por cada enlace de evento.
- La app permite descargar dos Exceles listos para análisis.

## Nota técnica

El sitio de PULEP puede cambiar su estructura HTML o mecanismos de consulta. Si eso ocurre, se requiere ajustar funciones de parseo en `scraper.py`.
