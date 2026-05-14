"""
LLM Service — Gateway architecture with intent classification + specialized handlers.

Flow: User Query  ->  Gateway Classifier  ->  Route to specialized prompt  ->  Response
"""
import json, re
from typing import Dict, Any, Optional, List
from openai import OpenAI

# ─── STAGE 1: LIGHTWEIGHT GATEWAY CLASSIFIER ───
# This prompt is tiny and focused — it ONLY classifies intent, nothing else.
GATEWAY_PROMPT = """You are a query classifier. Classify the user's message into exactly one category.

Data context available: {has_data}
{schema_hint}

CATEGORIES:
- GENERAL_CHAT: Greetings, general knowledge, chitchat, anything NOT about the uploaded data. Examples: "hello", "what is the capital of India", "how are you"
- DATA_QUERY: ANY question about the data that can be answered with SQL (counting, filtering, grouping, ranking, comparing, averages, etc). This is the DEFAULT for data questions.
  Examples: "how many students per hostel", "average CPI", "top 10 by CPI", "which hostel has the best students", "are smarter students in certain hostels", "which hostel should I choose for high CPI", "compare hostels by CPI", "who is the topper", "which category has the most", "show me everything", "standard deviation", "variance", "median", "top 10 and bottom 10"
- CHART: User EXPLICITLY wants a chart/graph/plot/visualization. Must mention visual words like chart, graph, plot, visualize, histogram, box plot, draw.
  Examples: "bar chart of X", "show me a pie chart", "plot CPI", "visualize", "draw a graph", "histogram of CPI", "box plot of CPI grouped by hostel"
- EXPLAIN: User wants to understand the WHOLE dataset. Examples: "explain this excel", "what is this data about", "describe the dataset"
- CORRELATION: User EXPLICITLY says "correlation" or "correlation matrix". Examples: "show correlations", "correlation matrix"
- OUTLIER: User EXPLICITLY says "outlier" or "anomaly". Examples: "find outliers", "detect anomalies"
- TIME_SERIES: User mentions "time series", "ARIMA", "stationary", "stationarity", "forecast", or "predict future/next". Examples: "time series analysis", "is the data stationary", "forecast next 12 months", "predict future values"
- PROJECTION: User says "project" values. Examples: "project next 6 values"
- SUGGESTION: User EXPLICITLY asks for "suggestions" or "what should I analyze". Examples: "give me suggestions"

PRIORITY RULES (follow strictly):
1. If the user says "stationary", "stationarity", "forecast", "predict future"  ->  TIME_SERIES
2. If the question can be answered with a SQL GROUP BY, COUNT, AVG, MAX, MIN  ->  DATA_QUERY
3. Only use CORRELATION/OUTLIER/SUGGESTION if the user EXPLICITLY uses those exact words
4. Questions like "which X is best", "compare X by Y", "standard deviation", "variance"  ->  DATA_QUERY
5. "show me a chart" or "visualize" or "box plot"  ->  CHART. But "show me the data"  ->  DATA_QUERY

Respond with ONLY: {{"category": "<CATEGORY>"}}"""

# ─── STAGE 2: SPECIALIZED PROMPTS (one per intent) ───

SQL_PROMPT = """You are a SQL expert generating queries for SQLite.

Table: {table_name}
Schema:
{schema_string}

SQLite LIMITATIONS (CRITICAL — follow these):
- NO STDDEV(), STDEV(), VARIANCE(), MEDIAN() functions. They don't exist in SQLite.
- For standard deviation: calculate manually or just use AVG and (MAX-MIN) for spread.
- For variance: use AVG((col - mean) * (col - mean)) pattern or simpler approach.
- For median: use a subquery with LIMIT/OFFSET or just compute percentiles.
- UNION ALL: each SELECT in a UNION must NOT have its own ORDER BY. Wrap in subqueries.
  WRONG: SELECT * FROM t ORDER BY x LIMIT 5 UNION ALL SELECT * FROM t ORDER BY x DESC LIMIT 5
  RIGHT: SELECT * FROM (SELECT * FROM t ORDER BY x LIMIT 5) UNION ALL SELECT * FROM (SELECT * FROM t ORDER BY x DESC LIMIT 5)

RULES:
- ONLY SELECT queries. Never INSERT/UPDATE/DELETE/DROP/CREATE/ALTER.
- Use exact column names from the schema.
- Use AS for calculated columns.
- For "top N" use ORDER BY + LIMIT.
- For "top and bottom" use subqueries with UNION ALL (wrap each in parentheses).
- Return ONLY valid JSON: {{"sql": "<SELECT query>"}}"""

CHART_PROMPT = """You are a chart configuration expert. The user wants a visualization.

Table: {table_name}
Schema:
{schema_string}

User request: "{user_message}"

RULES:
- Determine chart_type: line/bar/pie/scatter/histogram/box/heatmap. Default: "bar".
- Pick x and y columns from the schema. Use EXACT column names.
- IMPORTANT: If the user wants to see "how many" or "count" or "number of" items per category:
  Set y to ["__COUNT__"] — this tells the system to count rows per x category.
  Example: "bar chart of students per hostel"  ->  x="alloted_hostel", y=["__COUNT__"], chart_type="bar"
  Example: "pie chart of hostel distribution"  ->  x="alloted_hostel", y=["__COUNT__"], chart_type="pie"
- If user wants averages/sums of a numeric column per category, use that numeric column as y.
  Example: "average CPI per hostel"  ->  x="alloted_hostel", y=["cpi"], chart_type="bar"
- For scatter plots, both x and y should be numeric columns.
- For histogram, set y to the numeric column to show distribution of.
- Generate a descriptive title.

Return ONLY valid JSON: {{"chart_type": "<type>", "x": "<column>", "y": ["<column or __COUNT__>"], "title": "<title>"}}"""

TIMESERIES_PROMPT_CLASSIFY = """You are a time-series configuration expert.

Schema:
{schema_string}

User request: "{user_message}"

Identify the date column and value column for time-series analysis.
Return ONLY valid JSON: {{"date_column": "<col>", "value_column": "<col>", "periods": <int>}}
If not sure about columns, leave them empty strings."""

RESPONSE_PROMPT = """Answer the user's question based on these SQL results.
Question: {question}
SQL: {sql}
Results: {results}

RULES:
- Give a SHORT, direct answer first (1-2 sentences max)
- Then optionally list key data points as brief bullets
- NO paragraphs. NO technical jargon. NO SQL mentions.
- Format numbers with commas. Round decimals to 2 places.
- If asked "which is best/highest/most", lead with THE answer."""

EXPLAIN_PROMPT = """You are a data analyst. Generate a clear explanation of this dataset.

Dataset Overview:
{overview}

Cover:
1. What this dataset is about (infer from column names and values)
2. Key statistics (rows, columns, types)
3. Notable patterns (distributions, top categories, nulls)
4. Potential analysis opportunities

Be specific — reference actual column names and values. Use plain text, no code fences."""

CORRELATION_PROMPT = """Summarize these correlation results in 3-5 bullet points MAX. Be brief.

{correlation_data}

Format: Start with the strongest pair, its value, and what it means. Then others. One line each."""

OUTLIER_PROMPT = """Summarize these outlier results in 3-5 bullet points MAX. Be brief.

{outlier_data}

Format: Which columns have outliers, how many, and one-line recommendation."""

TIMESERIES_EXPLAIN_PROMPT = """Summarize this time-series analysis in 3-5 bullet points MAX. Be brief.

{ts_data}

Cover trend direction, stationarity, forecast values, and recommendations."""


class LLMService:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    # ─── GATEWAY: Stage 1 ───
    def classify_intent(self, user_message: str, schema_string: str = "",
                        table_name: str = "", has_data: bool = True) -> Dict[str, Any]:
        """Lightweight gateway classifier — determines where to route the query."""
        schema_hint = f"Columns available: {schema_string[:500]}" if schema_string else "No data loaded."
        prompt = GATEWAY_PROMPT.format(
            has_data="Yes — Excel/CSV file is loaded" if has_data else "No data loaded",
            schema_hint=schema_hint
        )
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.0, max_tokens=100
            )
            parsed = self._extract_json(resp.choices[0].message.content.strip())
            if parsed and "category" in parsed:
                return {"intent": parsed["category"], "payload": {}}
            return {"intent": "GENERAL_CHAT", "payload": {}}
        except Exception as e:
            return {"intent": "GENERAL_CHAT", "payload": {"error": str(e)}}

    # ─── STAGE 2: Specialized handlers ───

    def generate_sql(self, user_message: str, schema_string: str, table_name: str) -> str:
        """Generate SQL from user question using dedicated SQL prompt."""
        prompt = SQL_PROMPT.format(schema_string=schema_string, table_name=table_name)
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1, max_tokens=500
            )
            parsed = self._extract_json(resp.choices[0].message.content.strip())
            if parsed and "sql" in parsed:
                return parsed["sql"]
            return ""
        except Exception as e:
            return ""

    def generate_chart_config(self, user_message: str, schema_string: str,
                               table_name: str) -> Dict[str, Any]:
        """Generate chart configuration from user request."""
        prompt = CHART_PROMPT.format(
            schema_string=schema_string, table_name=table_name,
            user_message=user_message
        )
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1, max_tokens=300
            )
            parsed = self._extract_json(resp.choices[0].message.content.strip())
            if parsed:
                return parsed
            return {"chart_type": "bar", "x": "", "y": [], "title": "Chart"}
        except:
            return {"chart_type": "bar", "x": "", "y": [], "title": "Chart"}

    def generate_timeseries_config(self, user_message: str, schema_string: str) -> Dict[str, Any]:
        """Extract time-series configuration from user request."""
        prompt = TIMESERIES_PROMPT_CLASSIFY.format(
            schema_string=schema_string, user_message=user_message
        )
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1, max_tokens=200
            )
            parsed = self._extract_json(resp.choices[0].message.content.strip())
            return parsed or {"date_column": "", "value_column": "", "periods": 12}
        except:
            return {"date_column": "", "value_column": "", "periods": 12}

    def general_chat(self, user_message: str) -> str:
        """Handle general conversation — greetings, knowledge questions, etc."""
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a friendly AI assistant that also specializes in data analysis. Answer the user's question naturally. If they greet you, greet back warmly. If they ask a general knowledge question, answer it. Keep responses concise."},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.5, max_tokens=500
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"I'm having trouble responding right now: {str(e)}"

    def generate_nl_response(self, question: str, sql: str, results_text: str) -> str:
        """Convert SQL results to natural language."""
        prompt = RESPONSE_PROMPT.format(question=question, sql=sql, results=results_text)
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful data analyst. Give clear, concise answers."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3, max_tokens=1000
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"Found data but had trouble formatting: {str(e)}"

    def generate_explain_response(self, overview: dict) -> str:
        """Generate dataset explanation."""
        prompt = EXPLAIN_PROMPT.format(overview=json.dumps(overview, indent=2, default=str))
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert data analyst."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3, max_tokens=1500
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"Dataset has {overview['shape']['rows']} rows and {overview['shape']['columns']} columns."

    def generate_correlation_response(self, correlation_data: dict) -> str:
        prompt = CORRELATION_PROMPT.format(correlation_data=json.dumps(correlation_data, indent=2, default=str))
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a data analyst."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3, max_tokens=1000
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"Correlation analysis completed. Error: {str(e)}"

    def generate_outlier_response(self, outlier_data: dict) -> str:
        prompt = OUTLIER_PROMPT.format(outlier_data=json.dumps(outlier_data, indent=2, default=str))
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a data analyst."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3, max_tokens=1000
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"Outlier detection completed. Error: {str(e)}"

    def generate_timeseries_response(self, ts_data: dict) -> str:
        safe_data = {k: v for k, v in ts_data.items() if k not in ('historical_series', 'historical_values')}
        prompt = TIMESERIES_EXPLAIN_PROMPT.format(ts_data=json.dumps(safe_data, indent=2, default=str))
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a data analyst."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3, max_tokens=1200
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"Time-series analysis completed. Error: {str(e)}"

    def generate_projection_explanation(self, column, historical, projected, method):
        prompt = f"Column: {column}, Method: {method}, History: {historical}, Projected: {projected}. Give 2-3 sentence explanation with trend and caveats."
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": "You are a data analyst."}, {"role": "user", "content": prompt}],
                temperature=0.3, max_tokens=500
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"Projection for {column}: {projected}"

    def generate_suggestions(self, schema_string, data_summary):
        prompt = f"Schema:\n{schema_string}\n\nStats:\n{data_summary}\n\nReturn 3-5 specific actionable suggestions as JSON array of strings only."
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": "You are a data analyst. Respond with JSON array only."}, {"role": "user", "content": prompt}],
                temperature=0.4, max_tokens=1000
            )
            parsed = self._extract_json(resp.choices[0].message.content.strip())
            return parsed if isinstance(parsed, list) else ["Unable to generate suggestions."]
        except Exception as e:
            return [f"Error: {str(e)}"]

    def _extract_json(self, text):
        text = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n?```\s*$', '', text, flags=re.MULTILINE).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            for pattern in [r'\{[\s\S]*\}', r'\[[\s\S]*\]']:
                m = re.search(pattern, text)
                if m:
                    try: return json.loads(m.group())
                    except: pass
            return None
