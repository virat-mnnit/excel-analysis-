"""
FastAPI Main Application — Routes for file upload, chat, and data analysis.
"""
import os, json, shutil, traceback
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

app = FastAPI(title="Excel Intelligence Chatbot", version="1.0.0")

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
    """Set the Grok API key."""
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
        # Clean up uploaded file
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass


@app.post("/api/chat")
async def chat(message: str = Form(...)):
    """Process a chat message — the main intelligence endpoint."""
    if not llm_service:
        raise HTTPException(status_code=400, detail="Please set your Grok API key first.")
    if not data_service.schema:
        raise HTTPException(status_code=400, detail="Please upload an Excel/CSV file first.")

    schema_string = data_service.get_schema_string()
    table_name = data_service.table_name

    try:
        # Step 1: Classify intent via LLM
        classification = llm_service.classify_intent(message, schema_string, table_name)
        intent = classification.get("intent", "UNSUPPORTED")
        payload = classification.get("payload", {})

        # Step 2: Route based on intent
        if intent == "DATA_QUERY":
            return await _handle_data_query(message, payload)
        elif intent == "CHART_REQUEST":
            return await _handle_chart_request(payload)
        elif intent == "PROJECTION":
            return await _handle_projection(payload)
        elif intent == "SUGGESTION":
            return await _handle_suggestion(payload, schema_string)
        else:
            msg = payload.get("message", "I'm not sure how to answer that with the available data.")
            return {"type": "text", "content": msg}

    except Exception as e:
        traceback.print_exc()
        return {"type": "error", "content": f"Something went wrong: {str(e)}"}


async def _handle_data_query(question: str, payload: dict):
    """Handle DATA_QUERY intent: sanitize SQL, execute, convert to NL."""
    sql = payload.get("sql", "")
    if not sql:
        return {"type": "text", "content": "I couldn't generate a query for that question."}

    try:
        clean_sql = sql_executor.sanitize(sql)
    except SQLSanitizationError as e:
        return {"type": "error", "content": f"Security check failed: {str(e)}"}

    try:
        columns, rows = data_service.execute_query(clean_sql)
    except Exception as e:
        return {"type": "error", "content": f"Query execution error: {str(e)}"}

    results_text = sql_executor.results_to_text(columns, rows)
    formatted = sql_executor.format_results(columns, rows)
    nl_response = llm_service.generate_nl_response(question, clean_sql, results_text)

    return {
        "type": "data_query",
        "content": nl_response,
        "sql": clean_sql,
        "table": formatted if formatted["total_rows"] > 0 else None
    }


async def _handle_chart_request(payload: dict):
    """Handle CHART_REQUEST intent: generate chart image."""
    chart_type = payload.get("chart_type", "bar")
    x_col = payload.get("x", "")
    y_cols = payload.get("y", [])
    title = payload.get("title", "Chart")

    if isinstance(y_cols, str):
        y_cols = [y_cols]

    df = data_service.get_dataframe()

    # Validate columns exist
    missing = [c for c in [x_col] + y_cols if c not in df.columns]
    if missing:
        return {"type": "error", "content": f"Column(s) not found: {', '.join(missing)}. Available: {', '.join(df.columns)}"}

    try:
        chart_b64 = chart_service.generate_chart(df, chart_type, x_col, y_cols, title)
        return {"type": "chart", "content": f"Here's your {chart_type} chart: {title}", "chart_image": chart_b64}
    except Exception as e:
        return {"type": "error", "content": f"Chart generation error: {str(e)}"}


async def _handle_projection(payload: dict):
    """Handle PROJECTION intent: run forecast and generate chart."""
    target = payload.get("target_column", "")
    method = payload.get("method", "linear")
    periods = payload.get("periods", 6)
    llm_explanation = payload.get("explanation", "")

    df = data_service.get_dataframe()
    if target not in df.columns:
        return {"type": "error", "content": f"Column '{target}' not found."}

    try:
        result = projection_service.project(df, target, method, periods)
        proj_chart = chart_service.generate_projection_chart(
            result["historical_series"], result["projected_values"], target
        )
        explanation = llm_service.generate_projection_explanation(
            target, str(result["historical_summary"]), result["projected_values"], method
        )
        return {
            "type": "projection",
            "content": explanation,
            "projected_values": result["projected_values"],
            "method": method,
            "periods": periods,
            "chart_image": proj_chart
        }
    except Exception as e:
        return {"type": "error", "content": f"Projection error: {str(e)}"}


async def _handle_suggestion(payload: dict, schema_string: str):
    """Handle SUGGESTION intent: return insights."""
    insights = payload.get("insights", [])
    if not insights:
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
    uvicorn.run(app, host="0.0.0.0", port=8000)
