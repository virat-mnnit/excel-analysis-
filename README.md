# 📊 Excel Intelligence Chatbot

> **AI-Powered Excel/CSV Analyst** — Upload a spreadsheet, ask questions in plain English, and get instant answers, charts, forecasts & optimization tips.

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?logo=openai&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 💬 **Natural Language Queries** | Ask questions like *"What is the total sales?"* — the AI converts it to SQL, runs it, and replies in plain English |
| 📈 **Chart Generation** | Request bar, line, pie, or scatter charts between any columns |
| 🔮 **Forecasting / Projections** | Predict future trends using linear regression or moving averages |
| 💡 **Smart Suggestions** | Get 3–5 actionable, data-specific optimization recommendations |
| 🔒 **SQL Safety** | Only SELECT queries allowed — all input is sanitized against injection |

---

## 🏗️ Architecture

```
User ──▶ Chat UI (HTML/JS) ──▶ FastAPI Backend
                                    │
                        ┌───────────┼───────────┐
                        ▼           ▼           ▼
                   OpenAI API   SQLite DB   Matplotlib
                  (GPT-4o-mini)  (pandas)   (Charts)
```

### Project Structure

```
excel-analysis/
├── backend/
│   ├── main.py                # FastAPI app & routes
│   ├── llm_service.py         # OpenAI integration & prompts
│   ├── data_service.py        # File parsing, schema inference, SQLite
│   ├── sql_executor.py        # SQL sanitization & execution
│   ├── chart_service.py       # Chart rendering (matplotlib)
│   ├── projection_service.py  # Forecasting engine (scikit-learn)
│   └── requirements.txt       # Python dependencies
├── frontend/
│   ├── index.html             # Chat UI
│   ├── style.css              # Dark-themed premium styling
│   └── app.js                 # Frontend logic
├── .gitignore
└── README.md
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.9+** installed ([Download](https://www.python.org/downloads/))
- **OpenAI API Key** ([Get one here](https://platform.openai.com/api-keys))
- **Git** (to clone the repo)

### 1. Clone the Repository

```bash
git clone https://github.com/virat-mnnit/excel-analysis-.git
cd excel-analysis-
```

### 2. Install Dependencies

```bash
pip install -r backend/requirements.txt
```

This installs:
| Package | Purpose |
|---------|---------|
| `fastapi` + `uvicorn` | Web server |
| `pandas` + `openpyxl` | Excel/CSV parsing |
| `sqlalchemy` | Database ORM |
| `openai` | GPT API client |
| `matplotlib` | Chart generation |
| `scikit-learn` + `numpy` | Forecasting (linear regression) |
| `python-multipart` | File upload handling |

### 3. Run the Server

```bash
cd backend
python main.py
```

The server starts at **http://localhost:8000**

### 4. Use the App

1. Open **http://localhost:8000** in your browser
2. Enter your **OpenAI API key** in the sidebar and click **Save API Key**
3. Upload an `.xlsx`, `.xls`, or `.csv` file
4. Start asking questions!

---

## 💬 Example Questions

Once your file is loaded, try asking:

```
📊 "What is the total and average of all numeric columns?"
📈 "Show me a bar chart of sales vs month"
🔍 "How many students scored above 80?"
🔮 "Predict the next 6 months of revenue"
💡 "What suggestions do you have to improve the numbers?"
📉 "Show a pie chart of category distribution"
🏆 "Which product has the highest sales?"
```

---

## ⚙️ Configuration

### Supported Models

| Model | Speed | Cost | Best For |
|-------|-------|------|----------|
| `gpt-4o-mini` | ⚡ Fast | 💰 Cheap | Default — great for most queries |
| `gpt-4o` | 🔄 Medium | 💰💰 Moderate | Complex analysis |
| `gpt-4.1-mini` | ⚡ Fast | 💰 Cheap | Latest mini model |
| `gpt-4.1-nano` | ⚡⚡ Fastest | 💰 Cheapest | Simple queries |

Select your preferred model from the dropdown in the sidebar.

### Supported File Formats

- `.xlsx` (Excel 2007+)
- `.xls` (Legacy Excel)
- `.csv` (Comma-separated values)

**Max recommended file size:** 50 MB

---

## 🔒 Security

- **SELECT-only SQL** — INSERT, UPDATE, DELETE, DROP, and other DML/DDL statements are blocked
- **Keyword blacklist** — 15+ dangerous SQL keywords are filtered
- **Multi-statement prevention** — Semicolons outside strings are rejected
- **API keys stay local** — Your OpenAI key is only sent to OpenAI's servers, never stored on disk

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **LLM** | OpenAI GPT-4o-mini (via `openai` SDK) |
| **Backend** | Python, FastAPI, Uvicorn |
| **Data Processing** | pandas, SQLAlchemy, SQLite (in-memory) |
| **Chart Rendering** | matplotlib |
| **Forecasting** | scikit-learn (LinearRegression), numpy |
| **Frontend** | Vanilla HTML, CSS, JavaScript |

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Run `pip install -r backend/requirements.txt` |
| `Port 8000 already in use` | Kill the process or change port in `main.py` |
| `API key error / 401` | Verify your OpenAI key at [platform.openai.com](https://platform.openai.com) |
| `"Not a zip file"` on upload | Your `.xlsx` file may be corrupted — try re-saving it from Excel |
| Large file slow to load | Files > 50MB use chunked loading — give it a moment |

---

## 📄 License

This project is open source under the [MIT License](LICENSE).

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

**Built with ❤️ by [virat-mnnit](https://github.com/virat-mnnit)**
