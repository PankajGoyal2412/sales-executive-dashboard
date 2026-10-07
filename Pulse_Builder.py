"""
Build the Sales Pulse front-end payload from data.xlsx.

Output shape used by templates/index.html:
  { D: columnar metric arrays, dims: label lookups, T: targets }
Cached to pulse_cache.json so page loads stay fast.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
XLSX_PATH = BASE_DIR / "data.xlsx"
CACHE_PATH = BASE_DIR / "pulse_cache.json"

# Dimension columns encoded as integer indexes into dims[key]
DIM_COLUMNS = [
    ("reg", "Region"),
    ("seg", "Segment"),
    ("ch", "Channel"),
    ("cat", "Product_Category"),
    ("sub", "Product_Subcategory"),
    ("prod", "Product"),
    ("cust", "Customer_Name"),
    ("rep", "Sales_Rep_ID"),
    ("ten", "Rep_Tenure"),
    ("camp", "Campaign"),
    ("ind", "Industry"),
]


def _encode_category(series: pd.Series):
    """Map unique values to 0..n-1 indexes. Returns (labels, row_indexes)."""
    labels = sorted(series.unique())
    index = {value: i for i, value in enumerate(labels)}
    return labels, [index[value] for value in series]


def _month_index(year, month):
    """Map calendar year/month onto a 0..23 index (2024=0..11, 2025=12..23)."""
    return (year - 2024) * 12 + month - 1


def build_pulse_payload() -> dict:
    """Read Excel and build the compact JSON payload the Pulse UI expects."""
    if not XLSX_PATH.exists():
        raise FileNotFoundError(
            f"data.xlsx not found at {XLSX_PATH}. Place the workbook next to app.py."
        )

    workbook = pd.ExcelFile(XLSX_PATH)
    sales = workbook.parse("Sales_Data")
    targets = workbook.parse("Monthly_Targets")

    if (sales.groupby("Sales_Rep_ID").Region.nunique() != 1).any():
        raise ValueError("Expected each Sales_Rep_ID to belong to exactly one Region")

    D: dict = {}
    dims: dict = {}
    for key, column in DIM_COLUMNS:
        dims[key], D[key] = _encode_category(sales[column])

    sales["mi"] = _month_index(sales["Year"], sales["Order_Date"].dt.month)
    D["mi"] = sales["mi"].tolist()
    D["u"] = sales["Units"].tolist()
    D["ns"] = sales["Net_Sales_INR"].round(0).astype(int).tolist()
    D["gp"] = sales["Gross_Profit_INR"].round(0).astype(int).tolist()
    D["ret"] = sales["Return_Amount_INR"].round(0).astype(int).tolist()
    D["ot"] = (sales["On_Time_Delivery_Flag"] == "Yes").astype(int).tolist()
    D["rf"] = (sales["Returned_Flag"] == "Yes").astype(int).tolist()
    D["disc"] = (sales["Discount_Pct"] * 10000).round().astype(int).tolist()
    D["nps"] = sales["NPS_Score"].tolist()

    targets["mi"] = _month_index(targets["Year"], targets["Month_Start"].dt.month)

    reps = dims["rep"]
    rep_meta = sales.drop_duplicates("Sales_Rep_ID").set_index("Sales_Rep_ID")
    dims["repname"] = [rep_meta.loc[r, "Sales_Rep"] for r in reps]
    dims["repreg"] = [dims["reg"].index(rep_meta.loc[r, "Region"]) for r in reps]
    dims["repten"] = [rep_meta.loc[r, "Rep_Tenure"] for r in reps]

    # Parent lookups used by drill-down charts
    dims["subcat"] = [
        dims["cat"].index(
            sales[sales.Product_Subcategory == sub].Product_Category.iloc[0]
        )
        for sub in dims["sub"]
    ]
    dims["prodsub"] = [
        dims["sub"].index(sales[sales.Product == prod].Product_Subcategory.iloc[0])
        for prod in dims["prod"]
    ]
    dims["custseg"] = [
        dims["seg"].index(sales[sales.Customer_Name == cust].Segment.iloc[0])
        for cust in dims["cust"]
    ]

    rep_index = {rep_id: i for i, rep_id in enumerate(reps)}
    T = [
        [
            rep_index[targets.Sales_Rep_ID.iloc[i]],
            int(targets.mi.iloc[i]),
            int(targets.Monthly_Sales_Target_INR.iloc[i]),
            int(targets.Monthly_GP_Target_INR.iloc[i]),
            int(targets.Units_Target.iloc[i]),
        ]
        for i in range(len(targets))
    ]

    return {"D": D, "dims": dims, "T": T}


def save_pulse_cache(payload: dict | None = None) -> dict:
    """Write pulse_cache.json and return the payload dict."""
    payload = payload or build_pulse_payload()
    # Escape "<" so values like "<1 year" cannot break the HTML <script> tag
    blob = json.dumps(payload, separators=(",", ":"), default=int).replace(
        "<", "\\u003c"
    )
    CACHE_PATH.write_text(blob, encoding="utf-8")
    return payload


def get_pulse_json(force: bool = False) -> str:
    """
    Return the Pulse payload as a JSON string.
    Rebuilds from Excel when forced, cache missing, or Excel is newer than cache.
    """
    need_rebuild = force or not CACHE_PATH.exists()
    if not need_rebuild and XLSX_PATH.exists():
        need_rebuild = XLSX_PATH.stat().st_mtime > CACHE_PATH.stat().st_mtime

    if need_rebuild:
        save_pulse_cache()

    return CACHE_PATH.read_text(encoding="utf-8")


if __name__ == "__main__":
    payload = save_pulse_cache()
    size_mb = CACHE_PATH.stat().st_size / 1e6
    print(f"Wrote {CACHE_PATH} ({size_mb:.2f} MB)")
    print(f"Order lines: {len(payload['D']['ns'])}, targets: {len(payload['T'])}")
