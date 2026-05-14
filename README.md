# Excel Intelligence — AI Data Analysis Platform

An advanced AI-powered data analysis platform built with FastAPI and OpenAI. Upload any Excel/CSV file and interact through natural language — ask questions, generate charts, detect outliers, run forecasts, and more. The system intelligently classifies your intent and routes it through specialized handlers for maximum accuracy.

---

## System Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Browser)                          │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ Chat UI  │  │ File Upload  │  │  Theme   │  │ Sample Chips  │  │
│  │ (app.js) │  │   (.xlsx)    │  │  Toggle  │  │  (category)   │  │
│  └────┬─────┘  └──────┬───────┘  └──────────┘  └───────────────┘  │
│       │               │                                            │
│       │  POST /api/chat          POST /api/upload                  │
└───────┼───────────────┼────────────────────────────────────────────┘
        │               │
        ▼               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     BACKEND (FastAPI — main.py)                    │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              STAGE 1: GATEWAY CLASSIFIER                      │ │
│  │     Lightweight LLM call (~100 tokens) — intent only          │ │
│  │                                                                │ │
│  │   User Query ──▶ LLM classifies ──▶ Returns category JSON    │ │
│  │                     {"category": "DATA_QUERY"}                │ │
│  └───────────────────────────┬────────────────────────────────────┘ │
│                              │                                      │
│                   ┌──────────┴──────────┐                          │
│                   │   Intent Router     │                          │
│                   └──────────┬──────────┘                          │
│          ┌───────┬───────┬───┴────┬────────┬────────┬──────┐      │
│          ▼       ▼       ▼        ▼        ▼        ▼      ▼      │
│   ┌──────────┐┌────┐┌───────┐┌────────┐┌───────┐┌─────┐┌─────┐  │
│   │DATA_QUERY││CHAT││ CHART ││EXPLAIN ││OUTLIER││T.S. ││CORR.│  │
│   └────┬─────┘└──┬─┘└───┬───┘└────┬───┘└───┬───┘└──┬──┘└──┬──┘  │
│        │         │      │         │        │       │      │      │
│  ┌─────┴──────────┴──────┴─────────┴────────┴───────┴──────┴───┐  │
│  │                   STAGE 2: SPECIALIZED HANDLERS              │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Stage 1 — Gateway Classifier

The gateway is a **tiny, zero-waste LLM call** that does ONE thing: classify the user's intent into a category. It uses ~100 tokens and returns a single JSON object.

```
Input:  "Which hostel has the highest average CPI?"
Output: {"category": "DATA_QUERY"}

Input:  "Draw a pie chart of hostel distribution"
Output: {"category": "CHART"}

Input:  "Is the CPI data stationary?"
Output: {"category": "TIME_SERIES"}

Input:  "Hello, how are you?"
Output: {"category": "GENERAL_CHAT"}
```

**Priority rules** are baked into the classifier prompt to prevent misrouting:
1. Statistical keywords ("stationary", "forecast", "predict") → `TIME_SERIES`
2. Any question answerable with SQL (GROUP BY, COUNT, AVG, compare) → `DATA_QUERY`
3. Only use CORRELATION/OUTLIER/SUGGESTION when user explicitly says those words
4. Visual words ("chart", "plot", "visualize", "box plot") → `CHART`

### Stage 2 — Specialized Handlers

Each intent category has its own **dedicated handler** with a task-specific LLM prompt, preventing the confusion of a single monolithic prompt.

---

### Intent Processing Pipelines

#### `DATA_QUERY` — The SQL Pipeline (Core)

This is the primary pipeline, preserved from the original design:

```
User Question
     │
     ▼
┌─────────────────────────┐
│  SQL Prompt (dedicated)  │  LLM generates SELECT query
│  - SQLite syntax rules   │  with column awareness
│  - No STDDEV/VARIANCE    │
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│  SQL Sanitizer           │  Blocks DROP/DELETE/INSERT
│  (sql_executor.py)       │  Prevents SQL injection
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│  SQLite Execution        │  Runs against in-memory DB
│  (data_service.py)       │  loaded from uploaded file
└────────────┬────────────┘
             │
             ├── Success ──▶ NLP Prompt ──▶ Natural Language Answer
             │
             └── Failure ──▶ Pandas Fallback (STDDEV, VARIANCE, MEDIAN)
                             Computes stats directly via df.std(), df.var()
```

**Pandas Fallback**: SQLite doesn't support `STDDEV()`, `VARIANCE()`, `MEDIAN()`, or complex `UNION ALL` with `ORDER BY`. When SQL execution fails with these errors, the system automatically falls back to computing the result using pandas and sends it through the NLP prompt.

#### `CHART` — Visualization Pipeline

```
User Request: "Bar chart of students per hostel"
     │
     ▼
┌──────────────────────────────┐
│  Chart Config Prompt          │  LLM extracts:
│  - chart_type: "bar"          │  - x column, y column(s)
│  - x: "alloted_hostel"        │  - __COUNT__ signal for aggregation
│  - y: ["__COUNT__"]           │  - title
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│  Smart Aggregation Engine     │
│  (main.py → _handle_chart)   │
│                               │
│  • __COUNT__ → value_counts() │  Groups by x, counts rows
│  • ID columns detected →     │  registration_no never summed
│    auto-fallback to count     │
│  • Categorical x + numeric y  │  Groups by x, takes mean of y
│  • Caps at 20 data points     │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│  Chart Renderer               │  matplotlib → base64 PNG
│  (chart_service.py)           │
│                               │
│  Premium styling:             │
│  - Dark/light theme aware     │
│  - Curated HSL color palette  │
│  - Value labels, trend lines  │
│  - Grouped box plots          │
└──────────────────────────────┘
```

**Supported Chart Types:**

| Type | Trigger Words | Special Behavior |
|------|--------------|------------------|
| `bar` | "bar chart", "compare" | Auto-aggregates categorical x |
| `line` | "line chart", "trend" | Connects points, fills area |
| `pie` | "pie chart", "proportion" | Always aggregates by count |
| `scatter` | "scatter plot" | Adds trend line |
| `histogram` | "histogram", "distribution" | KDE overlay curve |
| `box` | "box plot", "spread" | Grouped by x_col when categorical |
| `heatmap` | "heatmap" | Correlation matrix |

#### `TIME_SERIES` — Forecasting Pipeline

```
User: "Is the CPI data stationary?" / "Forecast next 10 values"
     │
     ▼
┌─────────────────────────────┐
│  Time-Series Config Prompt   │  LLM identifies:
│                              │  - date_column
│                              │  - value_column
│                              │  - forecast periods
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│  Auto-Detection Fallback     │  If LLM can't identify columns:
│  - Scans for 'date'/'time'  │  - Checks parseable datetime cols
│  - Picks first numeric col  │  - Falls back to index-based series
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│  Analytics Engine            │  ADF Stationarity Test
│  (analytics_service.py)      │  ARIMA(p,d,q) Fitting
│                              │  Trend Detection (linear)
│                              │  Rolling Statistics
│                              │  Future Forecasting
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│  Time-Series Chart           │  Historical + Forecast
│  (chart_service.py)          │  with confidence regions
└─────────────────────────────┘
```

#### `EXPLAIN` / `CORRELATION` / `OUTLIER`

```
EXPLAIN ──▶ analytics_service.explain_dataset()
            Full dataset profile: shape, types, nulls, duplicates,
            distributions, memory usage ──▶ LLM explanation

CORRELATION ──▶ analytics_service.compute_correlations()
                Pearson correlation matrix ──▶ Heatmap chart
                ──▶ LLM summary (3-5 bullet points)

OUTLIER ──▶ analytics_service.detect_outliers(method="iqr")
            IQR-based detection per numeric column
            ──▶ Box plot chart ──▶ LLM summary
```

#### `GENERAL_CHAT`

```
User: "Hello" / "What is machine learning?"
     │
     ▼
  LLM with conversational prompt (no data context needed)
     │
     ▼
  Text response — works even without any file uploaded
```

---

### Data Flow — End to End

```
┌──────────┐     ┌──────────────┐     ┌───────────────┐
│  Upload  │────▶│ pandas reads │────▶│ SQLite DB     │
│  .xlsx   │     │ into DataFrame│    │ (in-memory)   │
└──────────┘     └──────┬───────┘     └───────┬───────┘
                        │                     │
                        ▼                     ▼
                  Schema extracted      SQL queries run
                  (column names,        against this DB
                   types, sample)
                        │
                        ▼
                  Sent to LLM with
                  every classified
                  request for context
```

**Key design decisions:**
- DataFrame is kept in memory alongside SQLite for **dual access** — SQL for structured queries, pandas for statistical operations SQLite can't handle
- Schema string (column names + types) is attached to every LLM call so it always knows what columns exist
- File is processed once at upload, then all subsequent queries are instant

---

## Features

### Core Analysis
- **SQL-to-NLP Pipeline** — Ask questions in plain English, get SQL-powered answers with natural language explanations
- **Smart Intent Detection** — Gateway classifier routes queries to the right handler automatically
- **Pandas Fallback** — Statistical functions unsupported by SQLite (STDDEV, VARIANCE, MEDIAN) computed via pandas
- **General Conversation** — Chat naturally even without data loaded

### Visualization
- **7 Chart Types** — Bar, Line, Pie, Scatter, Histogram, Box Plot, Heatmap
- **Natural Language Charts** — Say "line chart of sales vs month" and it works
- **Smart Aggregation** — Automatically groups/counts data for pie/bar charts instead of plotting raw rows
- **Grouped Box Plots** — "Box plot of CPI by hostel" creates per-group comparison
- **Theme-Aware Rendering** — Charts adapt to dark/light mode
- **ID Column Detection** — Columns like registration_no are never summed/averaged, auto-falls back to counting

### Advanced Analytics
- **Dataset Explanation** — Full profiling: data types, distributions, nulls, duplicates
- **Correlation Analysis** — Pearson correlation matrix with heatmap visualization
- **Outlier Detection** — IQR and Z-score methods with box plot visualization
- **Time-Series Analysis** — ADF stationarity testing + ARIMA-based forecasting
- **Projections** — Linear regression-based numeric predictions

### Interface
- **Dark/Light Mode** — Toggle between themes (persisted in localStorage)
- **Sample Question Chips** — Categorized quick-start prompts
- **Responsive Design** — Works on desktop and mobile
- **ChatGPT-style UI** — Professional, clean, muted color palette

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Backend** | Python, FastAPI, Uvicorn | API server, request handling |
| **Database** | SQLite (in-memory) | SQL query execution on uploaded data |
| **LLM** | OpenAI API (GPT-4o / Grok) | Intent classification, SQL generation, NLP responses |
| **Data** | pandas, numpy | DataFrame operations, statistical fallback |
| **Statistics** | scipy, statsmodels | ADF test, ARIMA, KDE, linear regression |
| **ML** | scikit-learn | Linear regression for projections |
| **Charts** | matplotlib | All chart rendering, base64 export |
| **Frontend** | Vanilla HTML/CSS/JS | ChatGPT-inspired UI, dark/light themes |

---

## Getting Started

### Prerequisites

- **Python 3.9+** ([Download](https://www.python.org/downloads/))
- **OpenAI-compatible API Key** (OpenAI, xAI Grok, etc.)

### 1. Clone the Repository

```bash
git clone https://github.com/virat-mnnit/excel-analysis-.git
cd excel-analysis-
```

### 2. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Run the Server

```bash
python main.py
```

### 4. Open in Browser

Navigate to [http://localhost:8000](http://localhost:8000)

### 5. Configure & Use

1. Enter your API key in the sidebar
2. Upload an Excel/CSV file
3. Ask questions in plain English

---

## Project Structure

```
excel-analysis/
├── backend/
│   ├── main.py                # FastAPI app — gateway routing + intent handlers
│   ├── llm_service.py         # Gateway classifier + 9 specialized prompts
│   ├── data_service.py        # DataFrame management & SQLite engine
│   ├── sql_executor.py        # SQL sanitization, execution & formatting
│   ├── chart_service.py       # 7 chart types + heatmap + time-series charts
│   ├── analytics_service.py   # Correlation, outlier, time-series (ARIMA)
│   ├── projection_service.py  # Linear regression projections
│   └── requirements.txt       # Python dependencies
├── frontend/
│   ├── index.html             # Main HTML — sidebar + chat layout
│   ├── style.css              # CSS with dark/light theme variables
│   └── app.js                 # Chat logic, file upload, theme toggle
└── README.md
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serve frontend |
| `POST` | `/api/set-key` | Set API key, base URL, and model |
| `POST` | `/api/upload` | Upload Excel/CSV → loads into SQLite |
| `POST` | `/api/chat` | Main chat endpoint (gateway classifier) |
| `GET` | `/api/schema` | Get current data schema + sample |

---

## Supported Intent Categories

| Intent | Trigger | Example | Handler |
|--------|---------|---------|---------|
| `GENERAL_CHAT` | No data keywords | "Hello", "What is AI?" | Direct LLM chat |
| `DATA_QUERY` | SQL-answerable | "Average CPI per hostel" | SQL → Execute → NLP |
| `CHART` | Visual words | "Bar chart of X" | LLM config → Render |
| `EXPLAIN` | "explain", "describe" | "What is this data about?" | Dataset profiling |
| `CORRELATION` | "correlation" | "Show correlations" | Pearson matrix + heatmap |
| `OUTLIER` | "outlier", "anomaly" | "Find outliers in CPI" | IQR detection + box plot |
| `TIME_SERIES` | "stationary", "forecast" | "Is CPI stationary?" | ADF + ARIMA |
| `PROJECTION` | "project" | "Project next 6 values" | Linear regression |
| `SUGGESTION` | "suggestions" | "What should I analyze?" | LLM insights |

---

## Error Handling & Fallbacks

| Error | Cause | Fallback |
|-------|-------|----------|
| `no such function: STDDEV` | SQLite limitation | Pandas `df.std()` |
| `no such function: VARIANCE` | SQLite limitation | Pandas `df.var()` |
| `ORDER BY before UNION ALL` | Invalid SQL syntax | Pandas `nlargest` + `nsmallest` |
| Non-JSON LLM response | LLM hallucination | Regex extraction of JSON |
| `numpy.bool` serialization | NumPy types in JSON | Explicit `bool()`, `float()` casts |
| 749-row pie chart | No aggregation | Auto `value_counts()` |

---

## Dependencies

```
fastapi
uvicorn
python-multipart
pandas
openpyxl
openai
matplotlib
numpy
scipy
statsmodels
scikit-learn
```

---

## License

MIT
