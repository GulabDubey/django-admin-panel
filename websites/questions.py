"""
Per-visitor chatbot question limits (Website.question_limit / _period).

Each question is counted against the visitor's anonymous ID and, as a
backstop against visitors who clear their browser storage to get a new ID,
against a hash of their IP address with a larger allowance
(CHATBOT_IP_QUESTION_MULTIPLIER × the visitor limit).

Periods start at local-time boundaries (settings.TIME_ZONE): the hour, the
day, Monday, or the 1st of the month. "total" never resets.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Sum
from django.utils import timezone

from .models import QuestionUsage, Website

# Fixed period start for limits that never reset.
TOTAL_PERIOD_START = datetime(2000, 1, 1, tzinfo=timezone.get_fixed_timezone(0))

DEFAULT_LIMIT_MESSAGE = "You've reached the question limit for this chat. Please try again later."
DEFAULT_TOTAL_LIMIT_MESSAGE = "You've reached the question limit for this chat."


@dataclass(frozen=True)
class Period:
    start: datetime
    resets_at: datetime | None  # None = never


def current_period(period, now=None):
    now = timezone.localtime(now or timezone.now())
    if period == Website.PERIOD_TOTAL:
        return Period(TOTAL_PERIOD_START, None)
    if period == Website.PERIOD_HOUR:
        start = now.replace(minute=0, second=0, microsecond=0)
        return Period(start, start + timedelta(hours=1))
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == Website.PERIOD_WEEK:
        start = day - timedelta(days=day.weekday())
        return Period(start, _local(start.replace(tzinfo=None) + timedelta(days=7)))
    if period == Website.PERIOD_MONTH:
        start = day.replace(day=1)
        nxt = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
        return Period(start, _local(nxt.replace(tzinfo=None)))
    return Period(day, _local(day.replace(tzinfo=None) + timedelta(days=1)))


def _local(naive):
    # Re-localize so DST-observing zones get the correct offset at the boundary.
    return timezone.make_aware(naive, timezone.get_current_timezone())


@dataclass(frozen=True)
class Decision:
    allowed: bool
    limit: int  # 0 = unlimited
    remaining: int | None
    period: str
    resets_at: datetime | None
    reason: str = ""
    message: str = ""

    def as_json(self):
        data = {
            "allowed": self.allowed,
            "limit": self.limit,
            "remaining": self.remaining,
            "period": self.period,
            "resets_at": self.resets_at.astimezone(timezone.get_fixed_timezone(0)).strftime("%Y-%m-%dT%H:%M:%SZ")
            if self.resets_at else None,
        }
        if not self.allowed:
            data.update(reason=self.reason, message=self.message)
        return data


def _ip_limit(limit):
    multiplier = settings.CHATBOT_IP_QUESTION_MULTIPLIER
    return limit * multiplier if multiplier > 0 else 0


def _row(website, kind, identity, period_start):
    lookup = {"website": website, "kind": kind, "identity": identity, "period_start": period_start}
    try:
        with transaction.atomic():
            return QuestionUsage.objects.get_or_create(**lookup)[0]
    except IntegrityError:
        # Created concurrently by another request.
        return QuestionUsage.objects.get(**lookup)


def _increment_below(row, limit):
    """Atomically +1 unless the limit is reached. True if counted."""
    return QuestionUsage.objects.filter(pk=row.pk, count__lt=limit).update(count=F("count") + 1) == 1


def _denied(website, period, limit, reason):
    default = DEFAULT_TOTAL_LIMIT_MESSAGE if period.resets_at is None else DEFAULT_LIMIT_MESSAGE
    return Decision(
        allowed=False,
        limit=limit,
        remaining=0,
        period=website.question_limit_period,
        resets_at=period.resets_at,
        reason=reason,
        message=website.question_limit_message or default,
    )


def consume_question(website, visitor_id, ip_hash=""):
    """Count one question for this visitor, or refuse it if over the limit."""
    limit = website.question_limit
    period = current_period(website.question_limit_period)
    if limit <= 0:
        return Decision(True, 0, None, website.question_limit_period, None)

    visitor_row = _row(website, QuestionUsage.KIND_VISITOR, visitor_id, period.start)
    ip_limit = _ip_limit(limit)
    ip_row = _row(website, QuestionUsage.KIND_IP, ip_hash, period.start) if ip_hash and ip_limit else None

    with transaction.atomic():
        if not _increment_below(visitor_row, limit):
            return _denied(website, period, limit, "question_limit")
        if ip_row is not None and not _increment_below(ip_row, ip_limit):
            transaction.set_rollback(True)  # undo the visitor's +1
            return _denied(website, period, limit, "question_limit")

    used = QuestionUsage.objects.filter(pk=visitor_row.pk).values_list("count", flat=True).get()
    return Decision(True, limit, max(limit - used, 0), website.question_limit_period, period.resets_at)


def refund_question(website, visitor_id, ip_hash=""):
    """Give a question back (the reply failed). Never goes below zero."""
    period = current_period(website.question_limit_period)
    rows = QuestionUsage.objects.filter(website=website, period_start=period.start, count__gt=0)
    rows.filter(kind=QuestionUsage.KIND_VISITOR, identity=visitor_id).update(count=F("count") - 1)
    if ip_hash:
        rows.filter(kind=QuestionUsage.KIND_IP, identity=ip_hash).update(count=F("count") - 1)


def usage_summary(website):
    """Questions and distinct visitors in the current period (for the admin)."""
    period = current_period(website.question_limit_period)
    stats = QuestionUsage.objects.filter(
        website=website, kind=QuestionUsage.KIND_VISITOR, period_start=period.start, count__gt=0
    ).aggregate(questions=Sum("count"), visitors=Count("id"))
    at_limit = 0
    if website.question_limit > 0:
        at_limit = QuestionUsage.objects.filter(
            website=website, kind=QuestionUsage.KIND_VISITOR, period_start=period.start,
            count__gte=website.question_limit,
        ).count()
    return {
        "questions": stats["questions"] or 0,
        "visitors": stats["visitors"] or 0,
        "at_limit": at_limit,
        "period": period,
    }
