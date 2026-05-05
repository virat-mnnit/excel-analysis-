"""
SQL Executor — Sanitizes and executes SQL queries with strict safety enforcement.
"""

import re
from typing import Dict, Any, List, Tuple


# Dangerous SQL keywords that should NEVER appear in user queries
BLOCKED_KEYWORDS = [
    'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE',
    'EXEC', 'EXECUTE', 'MERGE', 'GRANT', 'REVOKE', 'COMMIT', 'ROLLBACK',
    'SAVEPOINT', 'BEGIN', 'ATTACH', 'DETACH', 'PRAGMA', 'VACUUM',
    'REPLACE INTO', 'LOAD', 'IMPORT'
]


class SQLSanitizationError(Exception):
    """Raised when SQL contains blocked operations."""
    pass


class SQLExecutor:
    """Sanitizes and executes SQL queries safely."""

    @staticmethod
    def sanitize(sql: str) -> str:
        """
        Validate that the SQL query is a safe SELECT-only statement.

        Raises SQLSanitizationError if dangerous keywords are found.
        """
        if not sql or not sql.strip():
            raise SQLSanitizationError("Empty SQL query.")

        cleaned = sql.strip().rstrip(';')

        # Remove comments
        cleaned_check = re.sub(r'--.*$', '', cleaned, flags=re.MULTILINE)
        cleaned_check = re.sub(r'/\*.*?\*/', '', cleaned_check, flags=re.DOTALL)

        upper_sql = cleaned_check.upper().strip()

        # Must start with SELECT or WITH (for CTEs)
        if not upper_sql.startswith('SELECT') and not upper_sql.startswith('WITH'):
            raise SQLSanitizationError(
                "Only SELECT queries are allowed. Your query must start with SELECT."
            )

        # Check for blocked keywords
        for keyword in BLOCKED_KEYWORDS:
            # Use word boundary matching to avoid false positives
            pattern = r'\b' + keyword.replace(' ', r'\s+') + r'\b'
            if re.search(pattern, upper_sql):
                raise SQLSanitizationError(
                    f"Blocked SQL operation detected: '{keyword}'. Only SELECT queries are permitted."
                )

        # Check for multiple statements (semicolons)
        # Allow semicolons inside string literals
        in_string = False
        quote_char = None
        for i, char in enumerate(cleaned):
            if char in ("'", '"') and (i == 0 or cleaned[i-1] != '\\'):
                if not in_string:
                    in_string = True
                    quote_char = char
                elif char == quote_char:
                    in_string = False
            elif char == ';' and not in_string:
                raise SQLSanitizationError(
                    "Multiple SQL statements are not allowed."
                )

        return cleaned

    @staticmethod
    def format_results(columns: list, rows: list, max_rows: int = 50) -> Dict[str, Any]:
        """
        Format query results into a structured response.
        Truncates large result sets.
        """
        truncated = False
        total_rows = len(rows)

        if total_rows > max_rows:
            rows = rows[:max_rows]
            truncated = True

        # Convert to list of dicts for JSON serialization
        result_dicts = []
        for row in rows:
            result_dicts.append(dict(zip(columns, row)))

        return {
            "columns": columns,
            "rows": result_dicts,
            "total_rows": total_rows,
            "truncated": truncated,
            "truncated_at": max_rows if truncated else None
        }

    @staticmethod
    def results_to_text(columns: list, rows: list, max_display: int = 10) -> str:
        """
        Convert query results to a text representation for LLM consumption.
        Summarizes if results are large.
        """
        if not rows:
            return "The query returned no results."

        total = len(rows)
        display_rows = rows[:max_display]

        lines = []
        lines.append(f"Query returned {total} row(s).")
        lines.append(f"Columns: {', '.join(columns)}")
        lines.append("")

        # Format as simple table
        for i, row in enumerate(display_rows):
            row_str = " | ".join([f"{col}: {val}" for col, val in zip(columns, row)])
            lines.append(f"Row {i+1}: {row_str}")

        if total > max_display:
            lines.append(f"\n... and {total - max_display} more rows (showing first {max_display}).")
            lines.append("Summary statistics may be more appropriate for large result sets.")

        return "\n".join(lines)
