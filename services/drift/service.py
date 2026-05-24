"""Drift detection service — baselines and behavioral analysis."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import NotFoundError
from common.models.baseline import AgentBaseline
from common.models.event import EventRecord
from common.schemas.drift import (
    AnalyzeRequest,
    BaselineCreate,
    DriftReportResponse,
    DriftScore,
    EventTypeDeviation,
)
from common.schemas.enums import SentinelType, Severity

_SEVERITY_THRESHOLDS = [
    (0.6, "high"),
    (0.4, "medium"),
    (0.2, "low"),
    (0.0, "none"),
]


def _score_to_severity(score: float) -> str:
    for threshold, label in _SEVERITY_THRESHOLDS:
        if score >= threshold:
            return label
    return "none"


class DriftDetectionService:
    def __init__(
        self,
        session: AsyncSession,
        sentinel_service: object | None = None,
    ) -> None:
        self._session = session
        self._sentinel = sentinel_service

    # ------------------------------------------------------------------
    # Baselines
    # ------------------------------------------------------------------

    async def compute_baseline(self, create: BaselineCreate) -> AgentBaseline:
        since = datetime.now(UTC) - timedelta(hours=create.lookback_hours)
        rows = await self._session.execute(
            select(EventRecord)
            .where(
                and_(
                    EventRecord.tenant_id == create.tenant_id,
                    EventRecord.agent_id == create.agent_id,
                    EventRecord.timestamp >= since,
                )
            )
            .order_by(EventRecord.timestamp.asc())
        )
        events = list(rows.scalars().all())

        counts: dict[str, int] = {}
        for e in events:
            counts[e.event_type] = counts.get(e.event_type, 0) + 1

        # Deactivate any existing active baselines for this agent.
        old_rows = await self._session.execute(
            select(AgentBaseline).where(
                and_(
                    AgentBaseline.tenant_id == create.tenant_id,
                    AgentBaseline.agent_id == create.agent_id,
                    AgentBaseline.is_active.is_(True),
                )
            )
        )
        for old in old_rows.scalars().all():
            old.is_active = False

        baseline = AgentBaseline(
            id=uuid4(),
            tenant_id=create.tenant_id,
            agent_id=create.agent_id,
            lookback_hours=create.lookback_hours,
            event_counts=counts,
            total_events=len(events),
            computed_at=datetime.now(UTC),
        )
        self._session.add(baseline)
        await self._session.commit()
        return baseline

    async def get_baseline(self, baseline_id: UUID) -> AgentBaseline:
        result = await self._session.execute(
            select(AgentBaseline).where(AgentBaseline.id == baseline_id)
        )
        baseline = result.scalar_one_or_none()
        if baseline is None:
            raise NotFoundError(f"Baseline {baseline_id} not found")
        return baseline

    async def list_baselines(
        self,
        tenant_id: str,
        agent_id: str | None = None,
        active_only: bool = True,
    ) -> list[AgentBaseline]:
        conditions = [AgentBaseline.tenant_id == tenant_id]
        if agent_id is not None:
            conditions.append(AgentBaseline.agent_id == agent_id)
        if active_only:
            conditions.append(AgentBaseline.is_active.is_(True))
        result = await self._session.execute(
            select(AgentBaseline)
            .where(and_(*conditions))
            .order_by(AgentBaseline.computed_at.desc())
        )
        return list(result.scalars().all())

    async def deactivate_baseline(self, baseline_id: UUID) -> AgentBaseline:
        baseline = await self.get_baseline(baseline_id)
        baseline.is_active = False
        await self._session.commit()
        return baseline

    # ------------------------------------------------------------------
    # Drift analysis
    # ------------------------------------------------------------------

    async def analyze(self, request: AnalyzeRequest) -> DriftReportResponse:
        baseline = await self._get_active_baseline(request.tenant_id, request.agent_id)

        since = datetime.now(UTC) - timedelta(hours=request.lookback_hours)
        rows = await self._session.execute(
            select(EventRecord)
            .where(
                and_(
                    EventRecord.tenant_id == request.tenant_id,
                    EventRecord.agent_id == request.agent_id,
                    EventRecord.timestamp >= since,
                )
            )
        )
        recent = list(rows.scalars().all())

        recent_counts: dict[str, int] = {}
        for e in recent:
            recent_counts[e.event_type] = recent_counts.get(e.event_type, 0) + 1

        score: float
        deviations: list[EventTypeDeviation]
        if baseline is None:
            score, deviations = 0.0, []
            severity = "none"
            baseline_id: UUID | None = None
            baseline_total = 0
        else:
            score, deviations = self._compute_tvd(
                baseline.event_counts,
                baseline.total_events,
                recent_counts,
                len(recent),
            )
            severity = _score_to_severity(score)
            baseline_id = baseline.id
            baseline_total = baseline.total_events

        alert_created = False
        if self._sentinel is not None and severity in ("medium", "high"):
            from common.schemas.sentinel import SentinelAlertCreate
            from services.sentinel.service import SentinelService

            sentinel: SentinelService = self._sentinel  # type: ignore[assignment]
            await sentinel.create_alert(
                SentinelAlertCreate(
                    tenant_id=request.tenant_id,
                    agent_id=request.agent_id,
                    sentinel_type=SentinelType.drift,
                    severity=Severity.high if severity == "high" else Severity.medium,
                    message=(
                        f"Drift detected for agent {request.agent_id}: "
                        f"score {score:.3f} ({severity})"
                    ),
                    details={
                        "score": round(score, 4),
                        "lookback_hours": request.lookback_hours,
                        "recent_event_count": len(recent),
                    },
                )
            )
            alert_created = True

        drift_score = DriftScore(
            tenant_id=request.tenant_id,
            agent_id=request.agent_id,
            score=round(score, 4),
            severity=severity,
            recent_event_count=len(recent),
            baseline_total_events=baseline_total,
            deviations=deviations,
        )
        return DriftReportResponse(
            drift_score=drift_score,
            baseline_id=baseline_id,
            alert_created=alert_created,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_active_baseline(
        self, tenant_id: str, agent_id: str
    ) -> AgentBaseline | None:
        result = await self._session.execute(
            select(AgentBaseline)
            .where(
                and_(
                    AgentBaseline.tenant_id == tenant_id,
                    AgentBaseline.agent_id == agent_id,
                    AgentBaseline.is_active.is_(True),
                )
            )
            .order_by(AgentBaseline.computed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _compute_tvd(
        baseline_counts: dict[str, int],
        baseline_total: int,
        recent_counts: dict[str, int],
        recent_total: int,
    ) -> tuple[float, list[EventTypeDeviation]]:
        """Compute Total Variation Distance between baseline and recent distributions."""
        if baseline_total == 0 or recent_total == 0:
            return 0.0, []

        all_types = sorted(set(baseline_counts.keys()) | set(recent_counts.keys()))
        deviations: list[EventTypeDeviation] = []
        tvd: float = 0.0

        for et in all_types:
            b_freq = baseline_counts.get(et, 0) / baseline_total
            r_freq = recent_counts.get(et, 0) / recent_total
            delta = abs(b_freq - r_freq)
            tvd += delta
            if delta > 0.001:
                deviations.append(
                    EventTypeDeviation(
                        event_type=et,
                        baseline_freq=round(b_freq, 4),
                        recent_freq=round(r_freq, 4),
                        delta=round(delta, 4),
                    )
                )

        return min(tvd / 2.0, 1.0), deviations
