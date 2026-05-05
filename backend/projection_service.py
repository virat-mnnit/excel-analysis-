"""
Projection Service — Handles forecasting using linear regression and moving averages.
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple
from sklearn.linear_model import LinearRegression


class ProjectionService:
    """Generates projections/forecasts for numeric data columns."""

    @staticmethod
    def project(df: pd.DataFrame, target_column: str, method: str = "linear",
                periods: int = 6) -> Dict[str, Any]:
        """
        Generate a projection for the target column.

        Args:
            df: Source DataFrame
            target_column: Column to project
            method: 'linear' for linear regression, 'trend' for moving average
            periods: Number of future periods to project

        Returns:
            Dict with projected_values, historical_summary, method used
        """
        if target_column not in df.columns:
            raise ValueError(f"Column '{target_column}' not found.")

        series = pd.to_numeric(df[target_column], errors='coerce').dropna()
        if len(series) < 3:
            raise ValueError(f"Not enough data points in '{target_column}' for projection (need at least 3).")

        values = series.values
        historical_summary = {
            "count": len(values),
            "mean": round(float(np.mean(values)), 2),
            "min": round(float(np.min(values)), 2),
            "max": round(float(np.max(values)), 2),
            "std": round(float(np.std(values)), 2),
            "trend": "increasing" if values[-1] > values[0] else "decreasing"
        }

        if method == "linear":
            projected = ProjectionService._linear_regression(values, periods)
        else:
            projected = ProjectionService._moving_average(values, periods)

        return {
            "target_column": target_column,
            "method": method,
            "periods": periods,
            "projected_values": [round(v, 2) for v in projected],
            "historical_summary": historical_summary,
            "historical_series": series
        }

    @staticmethod
    def _linear_regression(values: np.ndarray, periods: int) -> List[float]:
        """Project using linear regression."""
        X = np.arange(len(values)).reshape(-1, 1)
        y = values
        model = LinearRegression()
        model.fit(X, y)
        future_X = np.arange(len(values), len(values) + periods).reshape(-1, 1)
        return model.predict(future_X).tolist()

    @staticmethod
    def _moving_average(values: np.ndarray, periods: int) -> List[float]:
        """Project using exponential moving average extrapolation."""
        window = min(5, len(values) // 2) if len(values) > 4 else 2
        ema = pd.Series(values).ewm(span=window).mean().values
        # Calculate average step from EMA
        steps = np.diff(ema[-window:])
        avg_step = np.mean(steps) if len(steps) > 0 else 0
        last_val = ema[-1]
        return [float(last_val + avg_step * (i + 1)) for i in range(periods)]

    @staticmethod
    def get_data_summary(df: pd.DataFrame) -> str:
        """Generate a statistical summary of the DataFrame for LLM consumption."""
        lines = []
        desc = df.describe(include='all')
        for col in df.columns:
            lines.append(f"\n{col}:")
            if col in desc.columns:
                for stat in desc.index:
                    val = desc.loc[stat, col]
                    if pd.notna(val):
                        lines.append(f"  {stat}: {val}")
            nunique = df[col].nunique()
            nulls = df[col].isnull().sum()
            lines.append(f"  unique_values: {nunique}")
            lines.append(f"  null_count: {nulls}")
        return "\n".join(lines)
