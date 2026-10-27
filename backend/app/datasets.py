"""Named source tables for the tools. Reading a dataset never changes the map."""

import pandas as pd

from backend.app.analysis import AnalysisError
from backend.app.data import Bundle
from backend.app.layers import UnknownLayer, layer_frame, layer_ids


def dataset_ids(bundle: Bundle) -> list[str]:
    return ["sites", "companies", *[name for name in layer_ids(bundle) if name != "sites"]]


def dataset_frame(bundle: Bundle, dataset_id: str) -> pd.DataFrame:
    if dataset_id == "sites":
        # Geometry derives from lon/lat; omit the stored teaching-only projected coordinates.
        return bundle.sites.drop(columns=["x", "y"], errors="ignore").join(
            bundle.companies.company_name, on="company_id").copy()
    if dataset_id == "companies":
        return bundle.companies.copy()
    try:
        return layer_frame(bundle, dataset_id).copy()
    except UnknownLayer:
        raise AnalysisError("unknown_dataset", f"Unknown dataset_id '{dataset_id}'.",
                            f"Available datasets: {', '.join(dataset_ids(bundle))}.") from None
