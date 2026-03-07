"""
Property search tool — loads CSV into pandas and provides filter-based querying.
"""

import os
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CSV_PATH = os.path.join(DATA_DIR, "properties.csv")

_df = None


def _load_data():
    global _df
    if _df is None or _df.empty:
        if not os.path.exists(CSV_PATH):
            return pd.DataFrame()
        _df = pd.read_csv(CSV_PATH)
        for col in ["price", "bedrooms", "bathrooms", "sqft"]:
            if col in _df.columns:
                _df[col] = pd.to_numeric(_df[col], errors="coerce")
    return _df


def reload_data():
    """Force reload of CSV data."""
    global _df
    _df = None
    return _load_data()


def _safe_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def search_properties(
    min_price=None, max_price=None,
    min_bedrooms=None, max_bedrooms=None,
    min_bathrooms=None,
    min_sqft=None,
    city=None, state=None, zip_code=None,
    limit=20,
    sort_by="price",
    sort_order="ascending",
    **_kwargs,
):
    """Search properties with optional filters. Returns top matches as list of dicts."""
    df = _load_data()
    if df.empty:
        return []

    mask = pd.Series(True, index=df.index)

    v = _safe_float(min_price)
    if v is not None:
        mask &= df["price"] >= v
    v = _safe_float(max_price)
    if v is not None:
        mask &= df["price"] <= v
    v = _safe_int(min_bedrooms)
    if v is not None:
        mask &= df["bedrooms"] >= v
    v = _safe_int(max_bedrooms)
    if v is not None:
        mask &= df["bedrooms"] <= v
    v = _safe_float(min_bathrooms)
    if v is not None:
        mask &= df["bathrooms"] >= v
    v = _safe_float(min_sqft)
    if v is not None:
        mask &= df["sqft"] >= v
    if city and str(city).strip():
        mask &= df["city"].str.lower() == str(city).lower().strip()
    if state and str(state).strip():
        mask &= df["state"].str.upper() == str(state).upper().strip()
    if zip_code and str(zip_code).strip():
        mask &= df["zip"].astype(str) == str(zip_code).strip()

    ascending = str(sort_order).lower() != "descending"
    sort_col = sort_by if sort_by in df.columns else "price"
    lim = _safe_int(limit) or 20

    results = df[mask].sort_values(sort_col, ascending=ascending).head(lim)
    return results.to_dict(orient="records")


def get_property_details(index):
    """Get details of a specific property by DataFrame index."""
    df = _load_data()
    if df.empty or index < 0 or index >= len(df):
        return None
    return df.iloc[index].to_dict()


def get_property_by_id(property_id):
    """Get a property by its ID field."""
    df = _load_data()
    if df.empty or "id" not in df.columns:
        return None
    matches = df[df["id"] == property_id]
    if matches.empty:
        return None
    row = matches.iloc[0].to_dict()
    # Clean NaN values
    return {k: (None if isinstance(v, float) and v != v else v) for k, v in row.items()}


def get_all_properties():
    """Get all properties as list of dicts."""
    df = _load_data()
    if df.empty:
        return []
    props = df.to_dict(orient="records")
    # Clean NaN values
    clean = []
    for p in props:
        clean.append({k: (None if isinstance(v, float) and v != v else v) for k, v in p.items()})
    return clean


# Tool schema for Gemini function calling
SEARCH_TOOL_SCHEMA = {
    "name": "search_properties",
    "description": (
        "Search for real estate property listings with optional filters. "
        "Returns matching properties with price, address, bedrooms, "
        "bathrooms, sqft, description, and image URL. "
        "Use sort_order='descending' for most expensive, largest, etc. "
        "Use limit=1 when user asks for 'the most expensive' or 'the best' single property."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "min_price": {
                "type": "number",
                "description": "Minimum property price in GBP",
            },
            "max_price": {
                "type": "number",
                "description": "Maximum property price in GBP",
            },
            "min_bedrooms": {
                "type": "integer",
                "description": "Minimum number of bedrooms",
            },
            "max_bedrooms": {
                "type": "integer",
                "description": "Maximum number of bedrooms",
            },
            "min_bathrooms": {
                "type": "number",
                "description": "Minimum number of bathrooms",
            },
            "min_sqft": {
                "type": "number",
                "description": "Minimum square footage",
            },
            "city": {
                "type": "string",
                "description": "City name to filter by",
            },
            "state": {
                "type": "string",
                "description": "Region/country (e.g. England, Scotland)",
            },
            "zip_code": {
                "type": "string",
                "description": "Postcode to filter by",
            },
            "limit": {
                "type": "integer",
                "description": "Number of results to return (use 1 for single best match, default 5)",
            },
            "sort_by": {
                "type": "string",
                "description": "Column to sort by: price, bedrooms, bathrooms, sqft (default: price)",
            },
            "sort_order": {
                "type": "string",
                "description": "Sort direction: ascending or descending (default: ascending). Use descending for most expensive, most bedrooms, etc.",
            },
        },
    },
}
