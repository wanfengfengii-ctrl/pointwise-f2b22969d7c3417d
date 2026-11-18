from archive.history import read
from archive.storage import ArchivePath

from .audit import build_review_evidence
from .delivery import HandoffReport, HandoffRow
from .thresholds import exceeds_threshold, validate_threshold


def report(path: ArchivePath, batch_id: int, threshold: int) -> HandoffReport:
    threshold = validate_threshold(threshold)
    batch = read(path, batch_id)
    rows = tuple(
        HandoffRow(evidence, exceeds_threshold(evidence.milliunits, threshold))
        for evidence in build_review_evidence(batch)
    )
    return HandoffReport(batch.batch_id, batch.order.order_id, batch.order.profile.revision_id, threshold, rows)
