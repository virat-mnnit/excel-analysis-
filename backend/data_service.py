"""
Data Service — Handles Excel/CSV upload, parsing, schema inference, and SQLite loading.
"""

import os
import re
import sqlite3
import pandas as pd
from typing import Dict, Any, Optional, Tuple


class DataService:
    """Manages the lifecycle of uploaded Excel/CSV data."""

    def __init__(self):
        self.connection: Optional[sqlite3.Connection] = None
        self.table_name: str = "uploaded_data"
        self.schema: Dict[str, str] = {}
        self.dataframe: Optional[pd.DataFrame] = None
        self.row_count: int = 0
        self.col_count: int = 0
        self.file_name: str = ""

    def _sanitize_column_name(self, col: str) -> str:
        """Sanitize column names: replace spaces/special chars with underscores."""
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', str(col).strip())
        sanitized = re.sub(r'_+', '_', sanitized)
        sanitized = sanitized.strip('_')
        if sanitized and sanitized[0].isdigit():
            sanitized = f"col_{sanitized}"
        if not sanitized:
            sanitized = "unnamed_column"
        return sanitized.lower()

    def _infer_sql_type(self, dtype) -> str:
        """Map pandas dtype to SQLite type string."""
        dtype_str = str(dtype)
        if 'int' in dtype_str:
            return 'INTEGER'
        elif 'float' in dtype_str:
            return 'REAL'
        elif 'datetime' in dtype_str:
            return 'TEXT'  # SQLite stores dates as TEXT
        elif 'bool' in dtype_str:
            return 'INTEGER'
        else:
            return 'TEXT'

    def load_file(self, file_path: str, file_name: str) -> Dict[str, Any]:
        """
        Load an Excel or CSV file into an in-memory SQLite database.

        Returns metadata about the loaded data including schema info.
        """
        self.file_name = file_name
        ext = os.path.splitext(file_name)[1].lower()

        # Read the file with pandas
        try:
            if ext == '.csv':
                # Try chunked reading for large files
                file_size = os.path.getsize(file_path)
                if file_size > 50 * 1024 * 1024:  # > 50MB
                    chunks = []
                    for chunk in pd.read_csv(file_path, chunksize=10000):
                        chunks.append(chunk)
                    self.dataframe = pd.concat(chunks, ignore_index=True)
                else:
                    self.dataframe = pd.read_csv(file_path)
            elif ext in ('.xlsx', '.xls'):
                file_size = os.path.getsize(file_path)
                self.dataframe = pd.read_excel(file_path, engine='openpyxl')
            else:
                raise ValueError(f"Unsupported file format: {ext}. Please upload .xlsx, .xls, or .csv files.")
        except Exception as e:
            raise ValueError(f"Error reading file: {str(e)}")

        # Drop completely empty rows and columns
        self.dataframe.dropna(how='all', inplace=True)
        self.dataframe.dropna(axis=1, how='all', inplace=True)

        # Sanitize column names
        original_cols = list(self.dataframe.columns)
        sanitized_cols = []
        seen = {}
        for col in original_cols:
            sanitized = self._sanitize_column_name(col)
            if sanitized in seen:
                seen[sanitized] += 1
                sanitized = f"{sanitized}_{seen[sanitized]}"
            else:
                seen[sanitized] = 0
            sanitized_cols.append(sanitized)
        self.dataframe.columns = sanitized_cols

        # Store dimensions
        self.row_count = len(self.dataframe)
        self.col_count = len(self.dataframe.columns)

        # Build schema
        self.schema = {}
        for col in self.dataframe.columns:
            self.schema[col] = self._infer_sql_type(self.dataframe[col].dtype)

        # Load into SQLite in-memory database
        if self.connection:
            self.connection.close()

        self.connection = sqlite3.connect(":memory:", check_same_thread=False)

        # Convert datetime columns to string for SQLite compatibility
        df_to_load = self.dataframe.copy()
        for col in df_to_load.columns:
            if pd.api.types.is_datetime64_any_dtype(df_to_load[col]):
                df_to_load[col] = df_to_load[col].astype(str)

        df_to_load.to_sql(self.table_name, self.connection, if_exists='replace', index=False)

        # Generate column mapping for display
        column_mapping = {orig: san for orig, san in zip(original_cols, sanitized_cols)}

        # Sample data (first 5 rows)
        sample = self.dataframe.head(5).to_dict(orient='records')

        return {
            "file_name": file_name,
            "table_name": self.table_name,
            "row_count": self.row_count,
            "col_count": self.col_count,
            "schema": self.schema,
            "column_mapping": column_mapping,
            "sample_data": sample,
            "file_size_mb": round(os.path.getsize(file_path) / (1024 * 1024), 2)
        }

    def get_schema_string(self) -> str:
        """Generate a human-readable schema string for the LLM prompt."""
        if not self.schema:
            return "No data loaded."
        lines = [f"Table: {self.table_name}"]
        lines.append(f"Total rows: {self.row_count}")
        lines.append("Columns:")
        for col, dtype in self.schema.items():
            # Add sample values for context
            sample_vals = self.dataframe[col].dropna().unique()[:5]
            sample_str = ", ".join([str(v) for v in sample_vals])
            lines.append(f"  - {col} ({dtype}): sample values = [{sample_str}]")
        return "\n".join(lines)

    def execute_query(self, sql: str) -> Tuple[list, list]:
        """
        Execute a SQL query and return (columns, rows).
        """
        if not self.connection:
            raise RuntimeError("No data loaded. Please upload a file first.")

        cursor = self.connection.cursor()
        cursor.execute(sql)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        return columns, rows

    def get_column_data(self, column_name: str) -> pd.Series:
        """Get a specific column's data as a pandas Series."""
        if self.dataframe is None:
            raise RuntimeError("No data loaded.")
        if column_name not in self.dataframe.columns:
            raise ValueError(f"Column '{column_name}' not found in data.")
        return self.dataframe[column_name]

    def get_dataframe(self) -> pd.DataFrame:
        """Return the loaded DataFrame."""
        if self.dataframe is None:
            raise RuntimeError("No data loaded.")
        return self.dataframe

    def cleanup(self):
        """Close the SQLite connection and free memory."""
        if self.connection:
            self.connection.close()
            self.connection = None
        self.dataframe = None
        self.schema = {}
