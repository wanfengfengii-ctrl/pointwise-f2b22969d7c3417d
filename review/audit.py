from dataclasses import dataclass

from archive.batches import ArchivedBatch


@dataclass(frozen=True, slots=True)
class ReviewEvidence:
    ticket_id: str
    channel: str
    started_at: int
    ended_at: int
    milliunits: int


def build_review_evidence(batch: ArchivedBatch) -> tuple[ReviewEvidence, ...]:
    return tuple(
        ReviewEvidence(sample.ticket_id, sample.channel, sample.started_at, sample.ended_at, sample.milliunits)
        for sample in batch.samples
    )
