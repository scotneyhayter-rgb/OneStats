"""Allow a DAILY recurrence for scheduled tasks (International Men's Cricket update).

0067 shipped ``scheduled_task`` with ``schedule_kind`` constrained to ``'weekly'`` only. The
International workspace's update moves from weekly (Saturday 04:00 Australia/Melbourne) to DAILY
(04:00 Australia/Melbourne), so this relaxes the check to permit ``'daily'`` as well. ``day_of_week``
is already nullable (it is unused for a daily schedule), so no column change is needed. Additive and
reversible; the down-revision is only safe once no row uses ``'daily'``.

Revision ID: 0068_scheduled_task_daily
Revises: 0067_scheduled_task
"""
from __future__ import annotations

from alembic import op

revision = "0068_scheduled_task_daily"
down_revision = "0067_scheduled_task"
branch_labels = None
depends_on = None


# The project's SQLAlchemy naming convention expands a CheckConstraint named "scheduled_task_kind_schedule"
# on table "scheduled_task" to this stored name.
_CK = "ck_scheduled_task_scheduled_task_kind_schedule"


def upgrade() -> None:
    op.execute(f"ALTER TABLE scheduled_task DROP CONSTRAINT {_CK}")
    op.execute(
        f"ALTER TABLE scheduled_task ADD CONSTRAINT {_CK} "
        "CHECK (schedule_kind in ('weekly','daily'))"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE scheduled_task DROP CONSTRAINT {_CK}")
    op.execute(
        f"ALTER TABLE scheduled_task ADD CONSTRAINT {_CK} "
        "CHECK (schedule_kind in ('weekly'))"
    )
