"""
Chart Service — Renders charts using matplotlib and returns base64-encoded images.
"""
import io, base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from typing import Dict, Any, List, Optional
import pandas as pd


class ChartService:
    """Generates charts from data based on LLM-extracted parameters."""

    # Premium color palette
    COLORS = ['#6366f1', '#ec4899', '#14b8a6', '#f59e0b', '#8b5cf6', '#06b6d4', '#f43f5e', '#10b981']
    BG_COLOR = '#0f172a'
    TEXT_COLOR = '#e2e8f0'
    GRID_COLOR = '#1e293b'

    @staticmethod
    def generate_chart(df: pd.DataFrame, chart_type: str, x_col: str, y_cols: List[str], title: str = "Chart") -> str:
        """
        Generate a chart and return as base64-encoded PNG.

        Args:
            df: The DataFrame containing the data
            chart_type: One of 'bar', 'line', 'pie', 'scatter'
            x_col: Column name for x-axis
            y_cols: List of column names for y-axis
            title: Chart title

        Returns:
            Base64-encoded PNG string
        """
        plt.style.use('default')
        fig, ax = plt.subplots(figsize=(10, 6))
        fig.patch.set_facecolor(ChartService.BG_COLOR)
        ax.set_facecolor(ChartService.BG_COLOR)

        # Style axes
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color(ChartService.GRID_COLOR)
        ax.spines['bottom'].set_color(ChartService.GRID_COLOR)
        ax.tick_params(colors=ChartService.TEXT_COLOR, labelsize=10)
        ax.xaxis.label.set_color(ChartService.TEXT_COLOR)
        ax.yaxis.label.set_color(ChartService.TEXT_COLOR)
        ax.grid(True, alpha=0.15, color=ChartService.TEXT_COLOR, linestyle='--')

        colors = ChartService.COLORS
        x_data = df[x_col]

        if chart_type == 'pie':
            ChartService._render_pie(ax, df, x_col, y_cols[0], colors, title)
        elif chart_type == 'bar':
            ChartService._render_bar(ax, df, x_col, y_cols, colors)
        elif chart_type == 'line':
            ChartService._render_line(ax, df, x_col, y_cols, colors)
        elif chart_type == 'scatter':
            ChartService._render_scatter(ax, df, x_col, y_cols, colors)
        else:
            ChartService._render_bar(ax, df, x_col, y_cols, colors)

        if chart_type != 'pie':
            ax.set_xlabel(x_col.replace('_', ' ').title(), fontsize=12, fontweight='bold')
            y_label = ', '.join([c.replace('_', ' ').title() for c in y_cols])
            ax.set_ylabel(y_label, fontsize=12, fontweight='bold')

        ax.set_title(title, fontsize=16, fontweight='bold', color=ChartService.TEXT_COLOR, pad=20)

        if chart_type != 'pie' and len(y_cols) > 1:
            legend = ax.legend(facecolor=ChartService.BG_COLOR, edgecolor=ChartService.GRID_COLOR,
                             labelcolor=ChartService.TEXT_COLOR, fontsize=10)

        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                   facecolor=ChartService.BG_COLOR, edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode('utf-8')

    @staticmethod
    def _render_bar(ax, df, x_col, y_cols, colors):
        x = np.arange(len(df[x_col]))
        width = 0.8 / len(y_cols)
        for i, col in enumerate(y_cols):
            offset = (i - len(y_cols)/2 + 0.5) * width
            bars = ax.bar(x + offset, pd.to_numeric(df[col], errors='coerce').fillna(0),
                         width, label=col.replace('_', ' ').title(), color=colors[i % len(colors)],
                         alpha=0.85, edgecolor='white', linewidth=0.5)
        ax.set_xticks(x)
        labels = [str(v)[:15] for v in df[x_col]]
        ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=9)

    @staticmethod
    def _render_line(ax, df, x_col, y_cols, colors):
        for i, col in enumerate(y_cols):
            y_data = pd.to_numeric(df[col], errors='coerce').fillna(0)
            ax.plot(df[x_col].astype(str), y_data, color=colors[i % len(colors)],
                   linewidth=2.5, marker='o', markersize=6, label=col.replace('_', ' ').title(),
                   markeredgecolor='white', markeredgewidth=1.5)
            ax.fill_between(range(len(y_data)), y_data, alpha=0.1, color=colors[i % len(colors)])
        ax.set_xticks(range(len(df[x_col])))
        labels = [str(v)[:15] for v in df[x_col]]
        ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=9)

    @staticmethod
    def _render_scatter(ax, df, x_col, y_cols, colors):
        for i, col in enumerate(y_cols):
            x_data = pd.to_numeric(df[x_col], errors='coerce').fillna(0)
            y_data = pd.to_numeric(df[col], errors='coerce').fillna(0)
            ax.scatter(x_data, y_data, c=colors[i % len(colors)], s=80, alpha=0.7,
                      edgecolors='white', linewidth=0.5, label=col.replace('_', ' ').title())

    @staticmethod
    def _render_pie(ax, df, x_col, y_col, colors, title):
        values = pd.to_numeric(df[y_col], errors='coerce').fillna(0)
        labels = [str(v)[:20] for v in df[x_col]]
        wedges, texts, autotexts = ax.pie(
            values, labels=labels, colors=colors[:len(values)],
            autopct='%1.1f%%', startangle=90, pctdistance=0.85,
            wedgeprops=dict(width=0.5, edgecolor=ChartService.BG_COLOR, linewidth=2)
        )
        for t in texts: t.set_color(ChartService.TEXT_COLOR); t.set_fontsize(10)
        for t in autotexts: t.set_color('white'); t.set_fontsize(9); t.set_fontweight('bold')

    @staticmethod
    def generate_projection_chart(historical: pd.Series, projected: list, column_name: str) -> str:
        """Generate a projection chart showing historical data + forecast."""
        fig, ax = plt.subplots(figsize=(10, 6))
        fig.patch.set_facecolor(ChartService.BG_COLOR)
        ax.set_facecolor(ChartService.BG_COLOR)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color(ChartService.GRID_COLOR)
        ax.spines['bottom'].set_color(ChartService.GRID_COLOR)
        ax.tick_params(colors=ChartService.TEXT_COLOR, labelsize=10)
        ax.grid(True, alpha=0.15, color=ChartService.TEXT_COLOR, linestyle='--')

        hist_vals = pd.to_numeric(historical, errors='coerce').dropna().values
        n_hist = len(hist_vals)
        n_proj = len(projected)

        ax.plot(range(n_hist), hist_vals, color='#6366f1', linewidth=2.5, marker='o',
               markersize=5, label='Historical', markeredgecolor='white', markeredgewidth=1)
        ax.fill_between(range(n_hist), hist_vals, alpha=0.1, color='#6366f1')

        proj_x = list(range(n_hist - 1, n_hist + n_proj))
        proj_y = [hist_vals[-1]] + projected
        ax.plot(proj_x, proj_y, color='#f59e0b', linewidth=2.5, marker='s',
               markersize=5, linestyle='--', label='Projected', markeredgecolor='white', markeredgewidth=1)
        ax.fill_between(proj_x, proj_y, alpha=0.1, color='#f59e0b')

        ax.axvline(x=n_hist - 1, color='#64748b', linestyle=':', alpha=0.5, linewidth=1)
        ax.set_title(f'{column_name.replace("_", " ").title()} — Forecast', fontsize=16,
                    fontweight='bold', color=ChartService.TEXT_COLOR, pad=20)
        ax.set_xlabel('Period', fontsize=12, fontweight='bold', color=ChartService.TEXT_COLOR)
        ax.set_ylabel(column_name.replace('_', ' ').title(), fontsize=12, fontweight='bold', color=ChartService.TEXT_COLOR)
        ax.legend(facecolor=ChartService.BG_COLOR, edgecolor=ChartService.GRID_COLOR,
                 labelcolor=ChartService.TEXT_COLOR)
        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                   facecolor=ChartService.BG_COLOR, edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode('utf-8')
