"""
Chart Service — Renders charts using matplotlib and returns base64-encoded images.
Supports: bar, line, pie, scatter, histogram, box, heatmap.
"""
import io, base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.colors as mcolors
import numpy as np
from typing import Dict, Any, List, Optional
import pandas as pd


class ChartService:
    """Generates charts from data based on LLM-extracted parameters."""

    # Premium color palette — curated HSL-based
    COLORS = [
        '#6366f1', '#ec4899', '#14b8a6', '#f59e0b',
        '#8b5cf6', '#06b6d4', '#f43f5e', '#10b981',
        '#a78bfa', '#fb923c', '#22d3ee', '#f472b6',
    ]
    BG_COLOR = '#0f172a'
    BG_COLOR_LIGHT = '#ffffff'
    CARD_COLOR = '#1e293b'
    TEXT_COLOR = '#e2e8f0'
    TEXT_COLOR_LIGHT = '#1e293b'
    GRID_COLOR = '#334155'
    GRID_COLOR_LIGHT = '#e2e8f0'

    @staticmethod
    def _setup_axes(fig, ax, theme='dark'):
        """Apply consistent premium styling to axes."""
        bg = ChartService.BG_COLOR if theme == 'dark' else ChartService.BG_COLOR_LIGHT
        text = ChartService.TEXT_COLOR if theme == 'dark' else ChartService.TEXT_COLOR_LIGHT
        grid = ChartService.GRID_COLOR if theme == 'dark' else ChartService.GRID_COLOR_LIGHT

        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color(grid)
        ax.spines['bottom'].set_color(grid)
        ax.tick_params(colors=text, labelsize=10)
        ax.xaxis.label.set_color(text)
        ax.yaxis.label.set_color(text)
        ax.grid(True, alpha=0.12, color=text, linestyle='--', linewidth=0.5)
        return bg, text, grid

    @staticmethod
    def generate_chart(df: pd.DataFrame, chart_type: str, x_col: str,
                       y_cols: List[str], title: str = "Chart",
                       theme: str = "dark") -> str:
        """
        Generate a chart and return as base64-encoded PNG.

        Args:
            df: The DataFrame containing the data
            chart_type: One of 'bar', 'line', 'pie', 'scatter', 'histogram', 'box', 'heatmap'
            x_col: Column name for x-axis
            y_cols: List of column names for y-axis
            title: Chart title
            theme: 'dark' or 'light'

        Returns:
            Base64-encoded PNG string
        """
        plt.style.use('default')
        fig, ax = plt.subplots(figsize=(11, 6.5))
        bg, text, grid = ChartService._setup_axes(fig, ax, theme)
        colors = ChartService.COLORS

        if chart_type == 'pie':
            ChartService._render_pie(ax, df, x_col, y_cols[0], colors, title, bg, text)
        elif chart_type == 'bar':
            ChartService._render_bar(ax, df, x_col, y_cols, colors)
        elif chart_type == 'line':
            ChartService._render_line(ax, df, x_col, y_cols, colors)
        elif chart_type == 'scatter':
            ChartService._render_scatter(ax, df, x_col, y_cols, colors)
        elif chart_type == 'histogram':
            ChartService._render_histogram(ax, df, y_cols, colors)
        elif chart_type == 'box':
            ChartService._render_box(ax, df, x_col, y_cols, colors, text, grid)
        else:
            ChartService._render_bar(ax, df, x_col, y_cols, colors)

        if chart_type not in ('pie', 'histogram', 'box'):
            ax.set_xlabel(x_col.replace('_', ' ').title(), fontsize=12, fontweight='bold')
            y_label = ', '.join([c.replace('_', ' ').title() for c in y_cols])
            ax.set_ylabel(y_label, fontsize=12, fontweight='bold')

        ax.set_title(title, fontsize=16, fontweight='bold', color=text, pad=20,
                     fontfamily='sans-serif')

        if chart_type not in ('pie', 'histogram', 'box') and len(y_cols) > 1:
            legend = ax.legend(facecolor=bg, edgecolor=grid,
                             labelcolor=text, fontsize=10,
                             framealpha=0.8, borderpad=1)

        plt.tight_layout()
        return ChartService._fig_to_base64(fig, bg)

    @staticmethod
    def _render_bar(ax, df, x_col, y_cols, colors):
        x = np.arange(len(df[x_col]))
        width = 0.7 / max(len(y_cols), 1)
        for i, col in enumerate(y_cols):
            offset = (i - len(y_cols) / 2 + 0.5) * width
            vals = pd.to_numeric(df[col], errors='coerce').fillna(0)
            bars = ax.bar(x + offset, vals, width,
                         label=col.replace('_', ' ').title(),
                         color=colors[i % len(colors)],
                         alpha=0.88, edgecolor='white', linewidth=0.3,
                         zorder=3)
            # Add value labels on top of bars for small datasets
            if len(df) <= 12:
                for bar in bars:
                    h = bar.get_height()
                    if h != 0:
                        ax.text(bar.get_x() + bar.get_width() / 2., h,
                               f'{h:,.0f}' if abs(h) >= 1 else f'{h:.2f}',
                               ha='center', va='bottom', fontsize=8,
                               color=colors[i % len(colors)], fontweight='bold')
        ax.set_xticks(x)
        labels = [str(v)[:18] for v in df[x_col]]
        ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=9)

    @staticmethod
    def _render_line(ax, df, x_col, y_cols, colors):
        for i, col in enumerate(y_cols):
            y_data = pd.to_numeric(df[col], errors='coerce').fillna(0)
            color = colors[i % len(colors)]
            ax.plot(df[x_col].astype(str), y_data, color=color,
                   linewidth=2.5, marker='o', markersize=5,
                   label=col.replace('_', ' ').title(),
                   markeredgecolor='white', markeredgewidth=1.5,
                   zorder=3)
            ax.fill_between(range(len(y_data)), y_data, alpha=0.06, color=color)
        ax.set_xticks(range(len(df[x_col])))
        labels = [str(v)[:18] for v in df[x_col]]
        ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=9)

    @staticmethod
    def _render_scatter(ax, df, x_col, y_cols, colors):
        for i, col in enumerate(y_cols):
            x_data = pd.to_numeric(df[x_col], errors='coerce').fillna(0)
            y_data = pd.to_numeric(df[col], errors='coerce').fillna(0)
            color = colors[i % len(colors)]
            ax.scatter(x_data, y_data, c=color, s=70, alpha=0.75,
                      edgecolors='white', linewidth=0.5,
                      label=col.replace('_', ' ').title(), zorder=3)
            # Add trend line
            if len(x_data) > 2:
                z = np.polyfit(x_data, y_data, 1)
                p = np.poly1d(z)
                x_line = np.linspace(x_data.min(), x_data.max(), 100)
                ax.plot(x_line, p(x_line), color=color, alpha=0.4,
                       linestyle='--', linewidth=1.5)

    @staticmethod
    def _render_pie(ax, df, x_col, y_col, colors, title, bg, text):
        values = pd.to_numeric(df[y_col], errors='coerce').fillna(0)
        labels = [str(v)[:20] for v in df[x_col]]
        wedges, texts, autotexts = ax.pie(
            values, labels=labels, colors=colors[:len(values)],
            autopct='%1.1f%%', startangle=90, pctdistance=0.82,
            wedgeprops=dict(width=0.45, edgecolor=bg, linewidth=2.5),
            textprops={'fontsize': 10}
        )
        for t in texts:
            t.set_color(text)
            t.set_fontsize(10)
        for t in autotexts:
            t.set_color('white')
            t.set_fontsize(8)
            t.set_fontweight('bold')

    @staticmethod
    def _render_histogram(ax, df, y_cols, colors):
        """Render histogram for distribution analysis."""
        for i, col in enumerate(y_cols):
            data = pd.to_numeric(df[col], errors='coerce').dropna()
            color = colors[i % len(colors)]
            n_bins = min(max(int(np.sqrt(len(data))), 10), 50)
            ax.hist(data, bins=n_bins, color=color, alpha=0.75,
                   edgecolor='white', linewidth=0.5,
                   label=col.replace('_', ' ').title(), zorder=3)
            # Add KDE line
            if len(data) > 10:
                from scipy.stats import gaussian_kde
                kde = gaussian_kde(data)
                x_range = np.linspace(data.min(), data.max(), 200)
                kde_vals = kde(x_range)
                # Scale KDE to match histogram
                bin_width = (data.max() - data.min()) / n_bins
                ax.plot(x_range, kde_vals * len(data) * bin_width,
                       color=color, linewidth=2, alpha=0.9, zorder=4)
        ax.set_xlabel('Value', fontsize=12, fontweight='bold')
        ax.set_ylabel('Frequency', fontsize=12, fontweight='bold')
        if len(y_cols) > 1:
            ax.legend()

    @staticmethod
    def _render_box(ax, df, x_col, y_cols, colors, text_color, grid_color):
        """Render box plot — supports grouping by x_col for per-category comparison."""
        data_to_plot = []
        labels = []

        # If x_col is categorical and y_cols has a numeric column → grouped box plot
        if x_col and x_col in df.columns and df[x_col].dtype == 'object' and y_cols:
            value_col = y_cols[0]
            if value_col in df.columns:
                groups = df[x_col].dropna().unique()
                for group in groups:
                    vals = pd.to_numeric(df[df[x_col] == group][value_col], errors='coerce').dropna()
                    if len(vals) > 0:
                        data_to_plot.append(vals.values)
                        labels.append(str(group)[:20])
        
        # Fallback: plot each y_col as a separate box
        if not data_to_plot:
            for col in y_cols:
                if col in df.columns:
                    vals = pd.to_numeric(df[col], errors='coerce').dropna()
                    if len(vals) > 0:
                        data_to_plot.append(vals.values)
                        labels.append(col.replace('_', ' ').title())

        if not data_to_plot:
            return

        bp = ax.boxplot(data_to_plot, labels=labels, patch_artist=True,
                       widths=0.5, showfliers=True,
                       flierprops=dict(marker='o', markerfacecolor='#f43f5e',
                                      markersize=4, alpha=0.5),
                       medianprops=dict(color='white', linewidth=2),
                       whiskerprops=dict(color=text_color, linewidth=1.2),
                       capprops=dict(color=text_color, linewidth=1.2))

        for i, patch in enumerate(bp['boxes']):
            patch.set_facecolor(colors[i % len(colors)])
            patch.set_alpha(0.8)
            patch.set_edgecolor('white')
            patch.set_linewidth(0.5)

        ax.set_ylabel(y_cols[0].replace('_', ' ').title() if y_cols else 'Value',
                      fontsize=12, fontweight='bold')
        if len(labels) > 5:
            ax.tick_params(axis='x', rotation=45)

    @staticmethod
    def generate_heatmap(corr_matrix: dict, columns: list,
                         title: str = "Correlation Heatmap",
                         theme: str = "dark") -> str:
        """Generate a correlation heatmap."""
        bg = ChartService.BG_COLOR if theme == 'dark' else ChartService.BG_COLOR_LIGHT
        text = ChartService.TEXT_COLOR if theme == 'dark' else ChartService.TEXT_COLOR_LIGHT

        n = len(columns)
        fig_size = max(8, min(n * 1.2, 16))
        fig, ax = plt.subplots(figsize=(fig_size, fig_size * 0.85))
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)

        # Build matrix array
        matrix = np.zeros((n, n))
        for i, row in enumerate(columns):
            for j, col in enumerate(columns):
                matrix[i][j] = corr_matrix.get(col, {}).get(row, 0)

        # Custom diverging colormap
        cmap = plt.cm.RdYlBu_r

        im = ax.imshow(matrix, cmap=cmap, vmin=-1, vmax=1, aspect='auto')

        # Add text annotations
        for i in range(n):
            for j in range(n):
                val = matrix[i][j]
                text_color_cell = 'white' if abs(val) > 0.5 else (text if theme == 'dark' else '#333')
                ax.text(j, i, f'{val:.2f}', ha='center', va='center',
                       fontsize=max(7, 12 - n // 3), color=text_color_cell,
                       fontweight='bold' if abs(val) > 0.7 else 'normal')

        ax.set_xticks(np.arange(n))
        ax.set_yticks(np.arange(n))
        labels = [c.replace('_', ' ').title()[:15] for c in columns]
        ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=10, color=text)
        ax.set_yticklabels(labels, fontsize=10, color=text)
        ax.set_title(title, fontsize=16, fontweight='bold', color=text, pad=20)

        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.ax.tick_params(colors=text, labelsize=9)
        cbar.set_label('Correlation', color=text, fontsize=11)

        plt.tight_layout()
        return ChartService._fig_to_base64(fig, bg)

    @staticmethod
    def generate_outlier_chart(df: pd.DataFrame, outlier_results: list,
                               theme: str = "dark") -> str:
        """Generate a box plot highlighting outliers."""
        bg = ChartService.BG_COLOR if theme == 'dark' else ChartService.BG_COLOR_LIGHT
        text = ChartService.TEXT_COLOR if theme == 'dark' else ChartService.TEXT_COLOR_LIGHT
        grid = ChartService.GRID_COLOR if theme == 'dark' else ChartService.GRID_COLOR_LIGHT

        cols_with_outliers = [r for r in outlier_results if r['outlier_count'] > 0]
        if not cols_with_outliers:
            cols_with_outliers = outlier_results[:6]
        cols_to_plot = [r['column'] for r in cols_with_outliers[:8]]

        fig, ax = plt.subplots(figsize=(11, 6.5))
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color(grid)
        ax.spines['bottom'].set_color(grid)
        ax.tick_params(colors=text, labelsize=10)
        ax.grid(True, alpha=0.1, color=text, linestyle='--')

        data_to_plot = []
        labels = []
        for col in cols_to_plot:
            vals = pd.to_numeric(df[col], errors='coerce').dropna()
            if len(vals) > 0:
                data_to_plot.append(vals.values)
                labels.append(col.replace('_', ' ').title()[:15])

        if data_to_plot:
            bp = ax.boxplot(data_to_plot, labels=labels, patch_artist=True,
                           widths=0.5, showfliers=True,
                           flierprops=dict(marker='D', markerfacecolor='#f43f5e',
                                          markersize=6, alpha=0.8,
                                          markeredgecolor='white', markeredgewidth=0.5),
                           medianprops=dict(color='white', linewidth=2),
                           whiskerprops=dict(color=text, linewidth=1.2),
                           capprops=dict(color=text, linewidth=1.2))

            for i, patch in enumerate(bp['boxes']):
                patch.set_facecolor(ChartService.COLORS[i % len(ChartService.COLORS)])
                patch.set_alpha(0.8)
                patch.set_edgecolor('white')
                patch.set_linewidth(0.5)

        ax.set_title('Outlier Detection — Box Plot Analysis', fontsize=16,
                     fontweight='bold', color=text, pad=20)
        ax.set_ylabel('Value', fontsize=12, fontweight='bold', color=text)
        if len(labels) > 4:
            ax.tick_params(axis='x', rotation=45)
        plt.tight_layout()
        return ChartService._fig_to_base64(fig, bg)

    @staticmethod
    def generate_timeseries_chart(historical_values: list, forecast_values: list,
                                  value_col: str, date_range: dict = None,
                                  theme: str = "dark") -> str:
        """Generate a time-series chart with historical data and forecast."""
        bg = ChartService.BG_COLOR if theme == 'dark' else ChartService.BG_COLOR_LIGHT
        text = ChartService.TEXT_COLOR if theme == 'dark' else ChartService.TEXT_COLOR_LIGHT
        grid = ChartService.GRID_COLOR if theme == 'dark' else ChartService.GRID_COLOR_LIGHT

        fig, ax = plt.subplots(figsize=(12, 6.5))
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color(grid)
        ax.spines['bottom'].set_color(grid)
        ax.tick_params(colors=text, labelsize=10)
        ax.grid(True, alpha=0.1, color=text, linestyle='--')

        n_hist = len(historical_values)
        n_fore = len(forecast_values)

        # Historical
        ax.plot(range(n_hist), historical_values, color='#6366f1', linewidth=2.5,
               marker='o', markersize=4, label='Historical',
               markeredgecolor='white', markeredgewidth=1, zorder=3)
        ax.fill_between(range(n_hist), historical_values, alpha=0.08, color='#6366f1')

        # Forecast
        if forecast_values:
            proj_x = list(range(n_hist - 1, n_hist + n_fore))
            proj_y = [historical_values[-1]] + forecast_values
            ax.plot(proj_x, proj_y, color='#f59e0b', linewidth=2.5, marker='s',
                   markersize=5, linestyle='--', label='Forecast',
                   markeredgecolor='white', markeredgewidth=1, zorder=3)
            ax.fill_between(proj_x, proj_y, alpha=0.08, color='#f59e0b')

            # Confidence band (±10% of forecast values)
            upper = [v * 1.1 for v in proj_y]
            lower = [v * 0.9 for v in proj_y]
            ax.fill_between(proj_x, lower, upper, alpha=0.06, color='#f59e0b')

        # Divider line
        ax.axvline(x=n_hist - 1, color='#64748b', linestyle=':', alpha=0.5, linewidth=1.5)
        ax.text(n_hist - 1, ax.get_ylim()[1] * 0.95, ' Forecast →',
               color='#f59e0b', fontsize=9, fontweight='bold', va='top')

        ax.set_title(f'{value_col.replace("_", " ").title()} — Time Series Analysis & Forecast',
                     fontsize=16, fontweight='bold', color=text, pad=20)
        ax.set_xlabel('Period', fontsize=12, fontweight='bold', color=text)
        ax.set_ylabel(value_col.replace('_', ' ').title(), fontsize=12,
                     fontweight='bold', color=text)
        ax.legend(facecolor=bg, edgecolor=grid, labelcolor=text,
                 fontsize=10, framealpha=0.8)

        plt.tight_layout()
        return ChartService._fig_to_base64(fig, bg)

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
        return ChartService._fig_to_base64(fig, ChartService.BG_COLOR)

    @staticmethod
    def _fig_to_base64(fig, bg_color):
        """Convert matplotlib figure to base64 PNG string."""
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                   facecolor=bg_color, edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode('utf-8')
