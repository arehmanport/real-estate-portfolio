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


def search_properties(
    min_price=None, max_price=None,
    min_bedrooms=None, max_bedrooms=None,
    min_bathrooms=None,
    min_sqft=None,
    city=None, state=None, zip_code=None,
    limit=20,
):
    """Search properties with optional filters. Returns top matches as list of dicts."""
    df = _load_data()
    if df.empty:
        return []

    mask = pd.Series(True, index=df.index)

    if min_price is not None:
        mask &= df["price"] >= float(min_price)
    if max_price is not None:
        mask &= df["price"] <= float(max_price)
    if min_bedrooms is not None:
        mask &= df["bedrooms"] >= int(min_bedrooms)
    if max_bedrooms is not None:
        mask &= df["bedrooms"] <= int(max_bedrooms)
    if min_bathrooms is not None:
        mask &= df["bathrooms"] >= float(min_bathrooms)
    if min_sqft is not None:
        mask &= df["sqft"] >= float(min_sqft)
    if city is not None:
        mask &= df["city"].str.lower() == city.lower()
    if state is not None:
        mask &= df["state"].str.upper() == state.upper()
    if zip_code is not None:
        mask &= df["zip"].astype(str) == str(zip_code)

    results = df[mask].sort_values("price", ascending=True).head(int(limit))
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
        "Returns up to 5 matching properties with price, address, bedrooms, "
        "bathrooms, sqft, description, listing URL, and image URL."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "min_price": {
                "type": "number",
                "description": "Minimum property price in dollars",
            },
            "max_price": {
                "type": "number",
                "description": "Maximum property price in dollars",
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
                "description": "State abbreviation (e.g. TX, CA)",
            },
            "zip_code": {
                "type": "string",
                "description": "ZIP code to filter by",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return (default 5)",
            },
        },
    },
}
