"""Small checks shared by the calculation tools."""

import pandas as pd

from backend.app.analysis import AnalysisError


def check_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in frame]
    if missing:
        raise AnalysisError("unknown_column", f"Unknown column(s): {', '.join(missing)}.",
                            f"Available columns: {', '.join(frame.columns)}.")


def check_numeric(frame: pd.DataFrame, columns: list[str]) -> None:
    check_columns(frame, columns)
    invalid = [column for column in columns if not pd.api.types.is_numeric_dtype(frame[column])]
    if invalid:
        raise AnalysisError("invalid_column_type", f"Expected numeric column(s): {', '.join(invalid)}.",
                            "Use numeric columns from the dataset schema.")


def check_output(frame: pd.DataFrame, column: str) -> None:
    if column in frame:
        raise AnalysisError("invalid_output_column", f"Column '{column}' already exists.",
                            "Choose a new output column name to preserve the input columns.")
