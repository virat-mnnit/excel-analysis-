"""
Analytics Service — Advanced data analysis: correlations, outlier detection,
time-series decomposition, and dataset explanation.
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from scipy import stats as sp_stats


class AnalyticsService:
    """Provides advanced analytical capabilities beyond basic SQL queries."""

    @staticmethod
    def explain_dataset(df: pd.DataFrame, file_name: str = "") -> Dict[str, Any]:
        """
        Generate a comprehensive dataset overview.

        Returns shape, column info, data types, null counts,
        statistical summaries, and sample rows.
        """
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        datetime_cols = df.select_dtypes(include=['datetime64']).columns.tolist()

        # Column details
        column_details = []
        for col in df.columns:
            detail = {
                "name": col,
                "dtype": str(df[col].dtype),
                "null_count": int(df[col].isnull().sum()),
                "null_pct": round(df[col].isnull().mean() * 100, 1),
                "unique_count": int(df[col].nunique()),
            }
            if col in numeric_cols:
                detail["min"] = float(df[col].min()) if not df[col].isnull().all() else None
                detail["max"] = float(df[col].max()) if not df[col].isnull().all() else None
                detail["mean"] = round(float(df[col].mean()), 2) if not df[col].isnull().all() else None
                detail["median"] = round(float(df[col].median()), 2) if not df[col].isnull().all() else None
                detail["std"] = round(float(df[col].std()), 2) if not df[col].isnull().all() else None
            elif col in categorical_cols:
                top_vals = df[col].value_counts().head(5).to_dict()
                detail["top_values"] = {str(k): int(v) for k, v in top_vals.items()}
            column_details.append(detail)

        # Basic statistics
        overview = {
            "file_name": file_name,
            "shape": {"rows": len(df), "columns": len(df.columns)},
            "memory_mb": round(df.memory_usage(deep=True).sum() / (1024 * 1024), 2),
            "numeric_columns": numeric_cols,
            "categorical_columns": categorical_cols,
            "datetime_columns": datetime_cols,
            "total_nulls": int(df.isnull().sum().sum()),
            "duplicate_rows": int(df.duplicated().sum()),
            "column_details": column_details,
            "sample_rows": df.head(5).to_dict(orient='records'),
        }
        return overview

    @staticmethod
    def compute_correlations(df: pd.DataFrame) -> Dict[str, Any]:
        """
        Compute Pearson correlation matrix for all numeric columns.

        Returns the full matrix and highlights the strongest pairs.
        """
        numeric_df = df.select_dtypes(include=[np.number])
        if numeric_df.shape[1] < 2:
            return {
                "error": "Need at least 2 numeric columns for correlation analysis.",
                "matrix": None,
                "top_pairs": [],
            }

        corr_matrix = numeric_df.corr(method='pearson')

        # Extract top correlated pairs (excluding self-correlation)
        pairs = []
        cols = corr_matrix.columns.tolist()
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                val = corr_matrix.iloc[i, j]
                if not np.isnan(val):
                    pairs.append({
                        "col_a": cols[i],
                        "col_b": cols[j],
                        "correlation": round(float(val), 4),
                        "strength": AnalyticsService._corr_strength(abs(val)),
                    })
        pairs.sort(key=lambda x: abs(x["correlation"]), reverse=True)

        return {
            "matrix": {col: {row: round(float(corr_matrix.loc[row, col]), 4)
                             for row in cols} for col in cols},
            "columns": cols,
            "top_pairs": pairs[:10],
            "total_numeric_cols": len(cols),
        }

    @staticmethod
    def _corr_strength(val: float) -> str:
        if val >= 0.8:
            return "Very Strong"
        elif val >= 0.6:
            return "Strong"
        elif val >= 0.4:
            return "Moderate"
        elif val >= 0.2:
            return "Weak"
        else:
            return "Very Weak"

    @staticmethod
    def detect_outliers(df: pd.DataFrame, method: str = "iqr") -> Dict[str, Any]:
        """
        Detect outliers in all numeric columns using IQR or Z-score method.
        """
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if not numeric_cols:
            return {"error": "No numeric columns found for outlier detection.", "results": []}

        results = []
        total_outliers = 0

        for col in numeric_cols:
            series = df[col].dropna()
            if len(series) < 4:
                continue

            if method == "zscore":
                z_scores = np.abs(sp_stats.zscore(series))
                outlier_mask = z_scores > 3
                outlier_indices = series.index[outlier_mask].tolist()
                threshold_info = "Z-score > 3"
            else:  # IQR
                q1 = series.quantile(0.25)
                q3 = series.quantile(0.75)
                iqr = q3 - q1
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr
                outlier_mask = (series < lower) | (series > upper)
                outlier_indices = series.index[outlier_mask].tolist()
                threshold_info = f"IQR bounds: [{round(float(lower), 2)}, {round(float(upper), 2)}]"

            outlier_values = series[outlier_mask].tolist()
            count = len(outlier_values)
            total_outliers += count

            results.append({
                "column": col,
                "method": method.upper(),
                "outlier_count": count,
                "outlier_pct": round(count / len(series) * 100, 2),
                "threshold": threshold_info,
                "outlier_values": [round(float(v), 2) for v in outlier_values[:20]],
                "stats": {
                    "mean": round(float(series.mean()), 2),
                    "median": round(float(series.median()), 2),
                    "std": round(float(series.std()), 2),
                    "min": round(float(series.min()), 2),
                    "max": round(float(series.max()), 2),
                },
            })

        return {
            "method": method.upper(),
            "total_outliers": total_outliers,
            "columns_analyzed": len(results),
            "results": results,
        }

    @staticmethod
    def time_series_analysis(
        df: pd.DataFrame,
        date_col: str,
        value_col: str,
        periods: int = 12,
    ) -> Dict[str, Any]:
        """
        Perform time-series analysis: trend detection, seasonality check,
        stationarity test (ADF), and ARIMA-based forecasting.
        """
        if date_col not in df.columns:
            return {"error": f"Date column '{date_col}' not found."}
        if value_col not in df.columns:
            return {"error": f"Value column '{value_col}' not found."}

        ts_df = df[[date_col, value_col]].copy()
        ts_df[date_col] = pd.to_datetime(ts_df[date_col], errors='coerce')
        ts_df.dropna(inplace=True)
        ts_df.sort_values(date_col, inplace=True)
        ts_df.set_index(date_col, inplace=True)

        series = pd.to_numeric(ts_df[value_col], errors='coerce').dropna()
        if len(series) < 10:
            return {"error": "Need at least 10 data points for time-series analysis."}

        # Trend detection
        x_vals = np.arange(len(series))
        slope, intercept, r_value, p_value, std_err = sp_stats.linregress(x_vals, series.values)
        trend = "increasing" if slope > 0 else "decreasing" if slope < 0 else "flat"

        # Stationarity test (ADF)
        try:
            from statsmodels.tsa.stattools import adfuller
            adf_result = adfuller(series.values, autolag='AIC')
            is_stationary = bool(adf_result[1] < 0.05)  # Cast numpy.bool → Python bool
            stationarity = {
                "is_stationary": is_stationary,
                "adf_statistic": round(float(adf_result[0]), 4),
                "p_value": round(float(adf_result[1]), 4),
                "interpretation": "Stationary (no unit root)" if is_stationary else "Non-stationary (has unit root)"
            }
        except ImportError:
            stationarity = {"is_stationary": None, "note": "statsmodels not available for ADF test"}

        # Rolling statistics
        window = min(max(len(series) // 5, 3), 12)
        rolling_mean = series.rolling(window=window).mean().dropna().tolist()
        rolling_std = series.rolling(window=window).std().dropna().tolist()

        # ARIMA forecast
        forecast_values = []
        model_params = {}
        try:
            from statsmodels.tsa.arima.model import ARIMA
            model = ARIMA(series.values, order=(1, 1, 1))
            fitted = model.fit()
            forecast = fitted.forecast(steps=periods)
            forecast_values = [round(float(v), 2) for v in forecast]
            model_params = {
                "order": "(1,1,1)",
                "aic": round(float(fitted.aic), 2),
                "bic": round(float(fitted.bic), 2),
            }
        except Exception as e:
            # Fallback to linear projection
            future_x = np.arange(len(series), len(series) + periods)
            forecast_values = [round(float(slope * x + intercept), 2) for x in future_x]
            model_params = {"method": "linear_fallback", "note": str(e)}

        return {
            "date_column": date_col,
            "value_column": value_col,
            "data_points": int(len(series)),
            "date_range": {
                "start": str(series.index[0]),
                "end": str(series.index[-1]),
            },
            "trend": {
                "direction": str(trend),
                "slope": round(float(slope), 4),
                "r_squared": round(float(r_value ** 2), 4),
                "p_value": round(float(p_value), 6),
            },
            "stationarity": stationarity,
            "statistics": {
                "mean": round(float(series.mean()), 2),
                "std": round(float(series.std()), 2),
                "min": round(float(series.min()), 2),
                "max": round(float(series.max()), 2),
            },
            "forecast": {
                "periods": int(periods),
                "values": forecast_values,
                "model_params": model_params,
            },
            "historical_values": [float(v) for v in series.values.tolist()],
        }

