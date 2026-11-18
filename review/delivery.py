import csv
from dataclasses import dataclass
from io import StringIO

from .audit import ReviewEvidence


@dataclass(frozen=True, slots=True)
class HandoffRow:
    evidence: ReviewEvidence
    above_threshold: bool


@dataclass(frozen=True, slots=True)
class HandoffReport:
    batch_id: int
    order_id: str
    revision_id: str
    threshold: int
    rows: tuple[HandoffRow, ...]


def _display_integer(value: int) -> str:
    try:
        return str(value)
    except ValueError:
        return hex(value)


def render_handoff(handoff: HandoffReport) -> str:
    output = StringIO(newline='')
    writer = csv.writer(output, delimiter='\t', lineterminator='\n')
    writer.writerow(('batch_id', 'order_id', 'revision_id', 'threshold_milliunits'))
    writer.writerow((handoff.batch_id, handoff.order_id, handoff.revision_id, _display_integer(handoff.threshold)))
    writer.writerow(('ticket_id', 'channel', 'started_at_s', 'ended_at_s', 'milliunits', 'above_threshold'))
    for row in handoff.rows:
        evidence = row.evidence
        writer.writerow((
            evidence.ticket_id, evidence.channel, evidence.started_at, evidence.ended_at,
            _display_integer(evidence.milliunits), 'yes' if row.above_threshold else 'no',
        ))
    return output.getvalue()
