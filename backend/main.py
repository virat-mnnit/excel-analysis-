"""
FastAPI Main Application — Gateway architecture for intent routing.
User Query → Gateway Classifier → Specialized Handler → Response
"""
import os, json, shutil, traceback
import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Optional

from data_service import DataService
from llm_service import LLMService
from sql_executor import SQLExecutor, SQLSanitizationError
from chart_service import ChartService
from projection_service import ProjectionService
from analytics_service import AnalyticsService

app = FastAPI(title="Excel Intelligence Chatbot", version="2.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global services
data_service = DataService()
llm_service: Optional[LLMService] = None
chart_service = ChartService()
projection_service = ProjectionService()
sql_executor = SQLExecutor()
analytics_service = AnalyticsService()

# Ensure upload dir exists
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Serve frontend
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# Mount static files for CSS/JS
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.post("/api/set-key")
async def set_api_key(api_key: str = Form(...), model: str = Form(default="grok-3-mini")):
    """Set the API key."""
    global llm_service
    try:
        llm_service = LLMService(api_key=api_key, model=model)
        return {"status": "success", "message": "API key configured successfully.", "model": model}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid API key: {str(e)}")


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload and process an Excel/CSV file."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ('.xlsx', '.xls', '.csv'):
        raise HTTPException(status_code=400, detail="Unsupported format. Upload .xlsx, .xls, or .csv")

    file_path = os.path.join(UPLOAD_DIR, file.filename)
    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        metadata = data_service.load_file(file_path, file.filename)
        return {"status": "success", "metadata": metadata}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass


@app.post("/api/chat")
async def chat(message: str = Form(...)):
    """Process a chat message — GATEWAY ARCHITECTURE.
    
    Stage 1: Lightweight classifier determines intent category
    Stage 2: Route to specialized handler with focused prompt
    """
    if not llm_service:
        raise HTTPException(status_code=400, detail="Please set your API key first.")

    has_data = bool(data_service.schema)
    schema_string = data_service.get_schema_string() if has_data else ""
    table_name = data_service.table_name if has_data else ""

    try:
        # ── Stage 1: Gateway Classification ──
        classification = llm_service.classify_intent(
            message, schema_string, table_name, has_data
        )
        intent = classification.get("intent", "GENERAL_CHAT")

        # ── Stage 2: Route to specialized handler ──

        # General chat — works without data
        if intent == "GENERAL_CHAT":
            return await _handle_general_chat(message)

        # Everything below requires data
        if not has_data:
            return {"type": "text", "content": "Please upload an Excel or CSV file first, then I can analyze it for you!"}

        if intent == "DATA_QUERY":
            return await _handle_data_query(message, schema_string, table_name)
        elif intent == "CHART":
            return await _handle_chart(message, schema_string, table_name)
        elif intent == "EXPLAIN":
            return await _handle_explain()
        elif intent == "CORRELATION":
            return await _handle_correlation()
        elif intent == "OUTLIER":
            return await _handle_outliers()
        elif intent == "TIME_SERIES":
            return await _handle_timeseries(message, schema_string)
        elif intent == "PROJECTION":
            return await _handle_projection_auto(message, schema_string)
        elif intent == "SUGGESTION":
            return await _handle_suggestion(schema_string)
        else:
            return await _handle_general_chat(message)

    except Exception as e:
        traceback.print_exc()
        return {"type": "error", "content": f"Something went wrong: {str(e)}"}


# ─── HANDLERS ───

async def _handle_general_chat(message: str):
    """Handle general conversation — no data required."""
    response = llm_service.general_chat(message)
    return {"type": "text", "content": response}


async def _handle_data_query(question: str, schema_string: str, table_name: str):
    """Handle DATA_QUERY: user question → SQL → execute → NL response.
    THIS IS THE PRESERVED PIPELINE: prompt → SQL → NLP to user.
    FALLBACK: If SQL fails (SQLite limitations), use pandas directly."""
    # Stage 2a: Generate SQL with dedicated SQL prompt
    sql = llm_service.generate_sql(question, schema_string, table_name)
    if not sql:
        return {"type": "text", "content": "I couldn't generate a query for that question. Try rephrasing it."}

    # Stage 2b: Sanitize SQL
    try:
        clean_sql = sql_executor.sanitize(sql)
    except SQLSanitizationError as e:
        return {"type": "error", "content": f"Security check failed: {str(e)}"}

    # Stage 2c: Execute SQL
    try:
        columns, rows = data_service.execute_query(clean_sql)
    except Exception as e:
        error_msg = str(e).lower()
        # ── PANDAS FALLBACK: Handle SQLite limitations ──
        if any(kw in error_msg for kw in ['stddev', 'stdev', 'variance', 'median', 'no such function']):
            return await _pandas_stats_fallback(question)
        if 'order by' in error_msg and 'union' in error_msg:
            return await _pandas_stats_fallback(question)
        return {"type": "error", "content": f"Query execution error: {str(e)}"}

    # Stage 2d: Convert results to NL
    results_text = sql_executor.results_to_text(columns, rows)
    formatted = sql_executor.format_results(columns, rows)
    nl_response = llm_service.generate_nl_response(question, clean_sql, results_text)

    return {
        "type": "data_query",
        "content": nl_response,
        "sql": clean_sql,
        "table": formatted if formatted["total_rows"] > 0 else None
    }


async def _pandas_stats_fallback(question: str):
    """Fallback: compute statistics using pandas when SQL can't handle it.
    Handles STDDEV, VARIANCE, MEDIAN, and complex queries SQLite doesn't support."""
    df = data_service.get_dataframe()
    q_lower = question.lower()
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()

    results = {}

    # Detect which stats are requested
    if 'standard deviation' in q_lower or 'std dev' in q_lower or 'stddev' in q_lower:
        stat_name = "Standard Deviation"
        for col in numeric_cols:
            results[col] = round(float(df[col].std()), 4)
    elif 'variance' in q_lower:
        stat_name = "Variance"
        for col in numeric_cols:
            results[col] = round(float(df[col].var()), 4)
    elif 'median' in q_lower:
        stat_name = "Median"
        for col in numeric_cols:
            results[col] = round(float(df[col].median()), 4)
    elif 'top' in q_lower and 'bottom' in q_lower:
        # "top 10 and bottom 10" type queries
        import re
        nums = re.findall(r'\d+', question)
        n = int(nums[0]) if nums else 10
        sort_col = numeric_cols[0] if numeric_cols else df.columns[0]
        # Find which column to sort by
        for col in df.columns:
            if col.lower() in q_lower:
                sort_col = col
                break
        top = df.nlargest(n, sort_col)
        bottom = df.nsmallest(n, sort_col)
        combined = pd.concat([top, bottom]).drop_duplicates()
        results_text = f"Top {n}:\n{top.to_string(index=False)}\n\nBottom {n}:\n{bottom.to_string(index=False)}"
        nl = llm_service.generate_nl_response(question, "pandas computation", results_text)
        # Build table
        table_cols = combined.columns.tolist()
        table_rows = combined.head(20).to_dict('records')
        return {
            "type": "data_query",
            "content": nl,
            "sql": "(computed via pandas — SQLite doesn't support this query)",
            "table": {"columns": table_cols, "rows": table_rows, "total_rows": len(table_rows)}
        }
    else:
        # Generic fallback — compute basic describe
        stat_name = "Statistics"
        desc = df[numeric_cols].describe().round(4) if numeric_cols else pd.DataFrame()
        results_text = desc.to_string()
        nl = llm_service.generate_nl_response(question, "pandas describe()", results_text)
        return {"type": "data_query", "content": nl, "sql": "(computed via pandas)", "table": None}

    # Check if it's per-group (e.g., "variance per hostel")
    group_col = None
    for col in df.columns:
        if df[col].dtype == 'object' and col.lower() in q_lower:
            group_col = col
            break
    # Also check for common keywords
    if not group_col:
        for col in df.columns:
            if df[col].dtype == 'object':
                col_words = col.lower().replace('_', ' ').split()
                if any(w in q_lower for w in col_words if len(w) > 2):
                    group_col = col
                    break

    if group_col and len(results) == 1:
        # Per-group stat for a specific column
        target_col = list(results.keys())[0]
        if 'standard deviation' in q_lower or 'stddev' in q_lower:
            grouped = df.groupby(group_col)[target_col].std().round(4).sort_values(ascending=False)
        elif 'variance' in q_lower:
            grouped = df.groupby(group_col)[target_col].var().round(4).sort_values(ascending=False)
        elif 'median' in q_lower:
            grouped = df.groupby(group_col)[target_col].median().round(4).sort_values(ascending=False)
        else:
            grouped = df.groupby(group_col)[target_col].describe().round(4)
        results_text = grouped.to_string()
    else:
        results_text = "\n".join(f"{col}: {val}" for col, val in results.items())

    nl = llm_service.generate_nl_response(question, f"pandas {stat_name.lower()}", results_text)

    return {
        "type": "data_query",
        "content": nl,
        "sql": f"(computed via pandas — {stat_name})",
        "table": None
    }


async def _handle_chart(message: str, schema_string: str, table_name: str):
    """Handle CHART: user request → dedicated chart prompt → generate chart.
    
    Smart aggregation: __COUNT__ signal, ID detection, auto-groupby.
    """
    config = llm_service.generate_chart_config(message, schema_string, table_name)

    chart_type = config.get("chart_type", "bar")
    x_col = config.get("x", "")
    y_cols = config.get("y", [])
    title = config.get("title", "Chart")

    if isinstance(y_cols, str):
        y_cols = [y_cols]

    df = data_service.get_dataframe()

    # ── Heatmap shortcut ──
    if chart_type == 'heatmap':
        corr_data = analytics_service.compute_correlations(df)
        if corr_data.get("error"):
            return {"type": "error", "content": corr_data["error"]}
        chart_b64 = chart_service.generate_heatmap(corr_data["matrix"], corr_data["columns"], title)
        return {"type": "chart", "content": f"Here's your correlation heatmap: {title}", "chart_image": chart_b64}

    # ── Histogram / Box — just need numeric columns ──
    if chart_type in ('histogram', 'box'):
        # Filter out __COUNT__ from y_cols
        real_y = [c for c in y_cols if c != '__COUNT__' and c in df.columns]
        if not real_y:
            real_y = df.select_dtypes(include=['number']).columns.tolist()[:4]
        try:
            chart_b64 = chart_service.generate_chart(df, chart_type, x_col, real_y, title)
            return {"type": "chart", "content": f"Here's your {chart_type} chart: {title}", "chart_image": chart_b64}
        except Exception as e:
            return {"type": "error", "content": f"Chart error: {str(e)}"}

    # ── Handle __COUNT__ signal: LLM says to count rows per category ──
    uses_count = '__COUNT__' in y_cols
    
    # Also detect if y_col is an ID-like column (not meaningful to sum/average)
    id_keywords = ['id', 'no', 'number', 'registration', 'transaction', 'reference', 'username']
    
    def is_id_column(col_name):
        return any(kw in col_name.lower() for kw in id_keywords)

    # ── Build the plot dataframe ──
    if x_col and x_col not in df.columns:
        return {"type": "error", "content": f"Column '{x_col}' not found. Available: {', '.join(df.columns)}"}

    plot_df = df
    
    if uses_count and x_col:
        # LLM explicitly asked for counting
        agg_df = df[x_col].value_counts().reset_index()
        agg_df.columns = [x_col, 'count']
        plot_df = agg_df
        y_cols = ['count']
    elif x_col and df[x_col].dtype == 'object' and len(df) > 20:
        # Categorical x-axis with many rows — must aggregate
        real_y = [c for c in y_cols if c in df.columns and c != '__COUNT__']
        
        if not real_y or all(is_id_column(c) for c in real_y):
            # No meaningful numeric y, or all y cols are IDs → count
            agg_df = df[x_col].value_counts().reset_index()
            agg_df.columns = [x_col, 'count']
            plot_df = agg_df
            y_cols = ['count']
        elif chart_type == 'pie':
            # Pie always counts categories
            agg_df = df[x_col].value_counts().reset_index()
            agg_df.columns = [x_col, 'count']
            plot_df = agg_df
            y_cols = ['count']
        else:
            # Aggregate numeric y by mean
            numeric_y = [c for c in real_y if pd.api.types.is_numeric_dtype(df[c])]
            if numeric_y:
                agg_df = df.groupby(x_col)[numeric_y].mean().round(2).reset_index()
                plot_df = agg_df
                y_cols = numeric_y
            else:
                agg_df = df[x_col].value_counts().reset_index()
                agg_df.columns = [x_col, 'count']
                plot_df = agg_df
                y_cols = ['count']

    # Cap data points for readability
    if len(plot_df) > 30 and chart_type in ('bar', 'line', 'pie'):
        plot_df = plot_df.head(20)

    # Validate final y_cols exist in plot_df
    y_cols = [c for c in y_cols if c in plot_df.columns]
    if not y_cols:
        y_cols = [c for c in plot_df.select_dtypes(include=['number']).columns if c != x_col][:1]
    if not y_cols:
        return {"type": "error", "content": "No numeric data to plot."}

    try:
        chart_b64 = chart_service.generate_chart(plot_df, chart_type, x_col, y_cols, title)
        return {"type": "chart", "content": f"Here's your {chart_type} chart: {title}", "chart_image": chart_b64}
    except Exception as e:
        return {"type": "error", "content": f"Chart generation error: {str(e)}"}


async def _handle_explain():
    """Handle EXPLAIN: provide comprehensive dataset overview."""
    df = data_service.get_dataframe()
    overview = analytics_service.explain_dataset(df, data_service.file_name)
    explanation = llm_service.generate_explain_response(overview)
    return {
        "type": "explain",
        "content": explanation,
        "metadata": {
            "rows": overview["shape"]["rows"],
            "columns": overview["shape"]["columns"],
            "numeric_cols": overview["numeric_columns"],
            "categorical_cols": overview["categorical_columns"],
            "total_nulls": overview["total_nulls"],
            "duplicate_rows": overview["duplicate_rows"],
            "memory_mb": overview["memory_mb"],
        }
    }


async def _handle_correlation():
    """Handle CORRELATION: compute and visualize correlations."""
    df = data_service.get_dataframe()
    corr_data = analytics_service.compute_correlations(df)
    if corr_data.get("error"):
        return {"type": "error", "content": corr_data["error"]}
    heatmap_b64 = chart_service.generate_heatmap(corr_data["matrix"], corr_data["columns"])
    explanation = llm_service.generate_correlation_response(corr_data)
    return {
        "type": "correlation",
        "content": explanation,
        "top_pairs": corr_data["top_pairs"],
        "chart_image": heatmap_b64,
    }


async def _handle_outliers():
    """Handle OUTLIER: detect and visualize outliers."""
    df = data_service.get_dataframe()
    outlier_data = analytics_service.detect_outliers(df, "iqr")
    if outlier_data.get("error"):
        return {"type": "error", "content": outlier_data["error"]}
    chart_b64 = chart_service.generate_outlier_chart(df, outlier_data["results"])
    explanation = llm_service.generate_outlier_response(outlier_data)
    return {
        "type": "outlier",
        "content": explanation,
        "total_outliers": outlier_data["total_outliers"],
        "results": outlier_data["results"],
        "chart_image": chart_b64,
    }


async def _handle_timeseries(message: str, schema_string: str):
    """Handle TIME_SERIES: full analysis with ARIMA."""
    # Get config from LLM
    config = llm_service.generate_timeseries_config(message, schema_string)
    date_col = config.get("date_column", "")
    value_col = config.get("value_column", "")
    periods = config.get("periods", 12)

    df = data_service.get_dataframe()

    # Auto-detect date column if not specified
    if not date_col:
        for col in df.columns:
            if any(kw in col.lower() for kw in ['date', 'time', 'year', 'month', 'day']):
                date_col = col
                break
        if not date_col:
            for col in df.columns:
                try:
                    pd_col = pd.to_datetime(df[col], errors='coerce')
                    if pd_col.notna().sum() > len(df) * 0.5:
                        date_col = col
                        break
                except:
                    pass
        if not date_col:
            return {"type": "error", "content": "Could not find a date/time column. Please specify which column contains dates."}

    # Auto-detect value column
    if not value_col:
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        if date_col in numeric_cols:
            numeric_cols.remove(date_col)
        if numeric_cols:
            value_col = numeric_cols[0]
        else:
            return {"type": "error", "content": "No numeric column found for time-series analysis."}

    ts_result = analytics_service.time_series_analysis(df, date_col, value_col, periods)
    if ts_result.get("error"):
        return {"type": "error", "content": ts_result["error"]}

    chart_b64 = chart_service.generate_timeseries_chart(
        ts_result["historical_values"], ts_result["forecast"]["values"],
        value_col, ts_result.get("date_range"),
    )
    explanation = llm_service.generate_timeseries_response(ts_result)
    return {
        "type": "timeseries",
        "content": explanation,
        "trend": ts_result["trend"],
        "stationarity": ts_result["stationarity"],
        "forecast": ts_result["forecast"],
        "statistics": ts_result["statistics"],
        "chart_image": chart_b64,
    }


async def _handle_projection_auto(message: str, schema_string: str):
    """Handle PROJECTION: auto-detect target column and project."""
    df = data_service.get_dataframe()
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    if not numeric_cols:
        return {"type": "error", "content": "No numeric columns available for projection."}
    target = numeric_cols[0]
    try:
        result = projection_service.project(df, target, "linear", 6)
        proj_chart = chart_service.generate_projection_chart(
            result["historical_series"], result["projected_values"], target
        )
        explanation = llm_service.generate_projection_explanation(
            target, str(result["historical_summary"]), result["projected_values"], "linear"
        )
        return {
            "type": "projection",
            "content": explanation,
            "projected_values": result["projected_values"],
            "method": "linear",
            "periods": 6,
            "chart_image": proj_chart,
        }
    except Exception as e:
        return {"type": "error", "content": f"Projection error: {str(e)}"}


async def _handle_suggestion(schema_string: str):
    """Handle SUGGESTION: return insights."""
    df = data_service.get_dataframe()
    summary = projection_service.get_data_summary(df)
    insights = llm_service.generate_suggestions(schema_string, summary)
    return {"type": "suggestion", "content": "Here are my data-driven suggestions:", "insights": insights}


@app.get("/api/schema")
async def get_schema():
    """Return the current data schema."""
    if not data_service.schema:
        raise HTTPException(status_code=400, detail="No data loaded.")
    return {
        "table_name": data_service.table_name,
        "schema": data_service.schema,
        "row_count": data_service.row_count,
        "col_count": data_service.col_count,
        "file_name": data_service.file_name
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
