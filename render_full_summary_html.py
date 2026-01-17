"""
Root wrapper for the report generator.

The implementation lives in `research/reports/render_full_summary_html.py`.
Keeping this wrapper means existing commands still work:

  python render_full_summary_html.py
"""

from research.reports.render_full_summary_html import main


if __name__ == "__main__":
    main()

