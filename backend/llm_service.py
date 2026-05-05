"""
LLM Service — OpenAI API integration for intent classification and NL generation.
"""
import json, re
from typing import Dict, Any, Optional
from openai import OpenAI

SYSTEM_PROMPT = """You are an intelligent data analysis assistant. Analyze user questions about their data.

Schema: {schema_string}
Table: {table_name}

RULES: Respond ONLY with valid JSON: {{ "intent": "<TYPE>", "payload": {{ ... }} }}

INTENT TYPES:
- DATA_QUERY: {{ "sql": "<SELECT query>" }}
- CHART_REQUEST: {{ "chart_type": "bar|line|pie|scatter", "x": "<col>", "y": ["<col1>"], "title": "<title>" }}
- PROJECTION: {{ "target_column": "<col>", "method": "linear|trend", "periods": <int>, "explanation": "<text>" }}
- SUGGESTION: {{ "insights": ["<s1>", "<s2>", ...] }}
- UNSUPPORTED: {{ "message": "<reason>" }}

SQL: Only SELECT. Never INSERT/UPDATE/DELETE/DROP/CREATE/ALTER. Use exact column names. Use AS for aliases.
CHARTS: pie for proportions, line for trends, bar for comparisons, scatter for correlations.
PROJECTIONS: Numeric columns only. Default 6 periods.
SUGGESTIONS: 3-5 specific, data-referenced suggestions. No generic advice.

Respond ONLY with JSON. No markdown, no code fences."""

RESPONSE_PROMPT = """Answer the user's question based on these SQL results.
Question: {question}
SQL: {sql}
Results: {results}
Be concise, friendly, conversational. No SQL or technical details. Format numbers nicely."""


class LLMService:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def classify_intent(self, user_message: str, schema_string: str, table_name: str) -> Dict[str, Any]:
        prompt = SYSTEM_PROMPT.format(schema_string=schema_string, table_name=table_name)
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user_message}],
                temperature=0.1, max_tokens=1500
            )
            parsed = self._extract_json(resp.choices[0].message.content.strip())
            if not parsed:
                return self._retry(user_message, prompt)
            if "intent" not in parsed:
                parsed = {"intent": "UNSUPPORTED", "payload": {"message": "Could not determine intent."}}
            return parsed
        except Exception as e:
            return {"intent": "UNSUPPORTED", "payload": {"message": f"LLM error: {str(e)}"}}

    def generate_nl_response(self, question: str, sql: str, results_text: str) -> str:
        prompt = RESPONSE_PROMPT.format(question=question, sql=sql, results=results_text)
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": "You are a helpful data analyst. Give clear answers."}, {"role": "user", "content": prompt}],
                temperature=0.3, max_tokens=1000
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"Found data but had trouble formatting: {str(e)}"

    def generate_projection_explanation(self, column, historical, projected, method):
        prompt = f"Column: {column}, Method: {method}, History: {historical}, Projected: {projected}. Give 2-3 sentence projection explanation with trend, values, and caveats."
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

    def _retry(self, msg, sys_prompt):
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": f"IMPORTANT: Valid JSON only.\n\n{msg}"}],
                temperature=0.0, max_tokens=1500
            )
            parsed = self._extract_json(resp.choices[0].message.content.strip())
            if parsed: return parsed
        except: pass
        return {"intent": "UNSUPPORTED", "payload": {"message": "Could not understand. Please rephrase."}}
