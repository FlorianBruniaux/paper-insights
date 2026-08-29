from __future__ import annotations

import json

from paper_insights.application.diagnostics import DoctorReport


def render_doctor(report: DoctorReport, *, as_json: bool) -> str:
    if as_json:
        return json.dumps(report.as_envelope(), sort_keys=True) + "\n"
    return f"doctor: {report.status}\n"
