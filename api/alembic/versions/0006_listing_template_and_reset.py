"""Standardized listing template columns + board reset to Rs 500 samples.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-06

Adds the standardized template fields every board entry now follows
(logo, property type, unit sizes, amenities, sample marker), then resets
the board: wipes all demo projects/bids from the launch-readiness pass and
seeds two clearly-marked sample entries (real Gurgaon project names, real
public RERA numbers, Rs 500 mock opening bid each) so the board restarts
from scratch at Rs 500.

The data wipe is one-way: the removed rows were seeded demo data with mock
payments only - no real money or real user listings existed at this point.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE projects ADD COLUMN logo_url TEXT")
    op.execute("ALTER TABLE projects ADD COLUMN property_type TEXT")
    op.execute("ALTER TABLE projects ADD COLUMN unit_sizes TEXT")
    op.execute("ALTER TABLE projects ADD COLUMN amenities TEXT")
    op.execute("ALTER TABLE projects ADD COLUMN is_sample BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute(
        """
        ALTER TABLE projects ADD CONSTRAINT ck_projects_property_type
        CHECK (property_type IS NULL OR property_type IN ('apartment','villa','townhouse'))
        """
    )

    # ---- board reset: clear all demo state, in FK-safe order ----
    op.execute("DELETE FROM leadership_log")
    op.execute("DELETE FROM bids")
    op.execute("DELETE FROM payment_intents")
    op.execute("DELETE FROM project_claims")
    op.execute("DELETE FROM project_disputes")
    op.execute("DELETE FROM projects")

    # ---- two sample entries, clearly marked, Rs 500 mock opening bid each ----
    op.execute(
        """
        INSERT INTO users (id, phone, display_name, is_verified, role)
        VALUES ('00000000-0000-0000-0000-00000000ff01', NULL,
                'Sample listings', TRUE, 'user')
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO projects
            (id, name, developer_name, locality, rera_number, rera_verified,
             project_url, logo_url, property_type, unit_sizes, amenities,
             is_sample, submitted_by, status, cached_total_paise, total_bid_count)
        VALUES
            ('00000000-0000-0000-0000-00000000aa01',
             'Godrej Meridien', 'Godrej Properties', 'Sector 106, Dwarka Expressway',
             'RC/REP/HARERA/GGM/393/125/2020/09', FALSE,
             'https://www.godrejproperties.com/gurugram/residential/godrej-meridien',
             NULL, 'apartment', '2, 3 & 4 BHK',
             'Clubhouse, Swimming pool, Gym, Kids'' play area',
             TRUE, '00000000-0000-0000-0000-00000000ff01', 'live', 50000, 1),
            ('00000000-0000-0000-0000-00000000aa02',
             'DLF The Camellias', 'DLF', 'Sector 42, Golf Course Road',
             'RC/REP/HARERA/GGM/2018/13', FALSE,
             'https://www.dlf.in/residential/the-camellias/',
             NULL, 'apartment', '4, 5 & 6 BHK',
             'Clubhouse, Swimming pool, Spa, Concierge',
             TRUE, '00000000-0000-0000-0000-00000000ff01', 'live', 50000, 1)
        """
    )
    op.execute(
        """
        INSERT INTO payment_intents
            (id, project_id, user_id, amount_paise, idempotency_key,
             razorpay_order_id, status)
        VALUES
            ('00000000-0000-0000-0000-00000000bb01',
             '00000000-0000-0000-0000-00000000aa01',
             '00000000-0000-0000-0000-00000000ff01',
             50000, 'opening-sample-aa01', NULL, 'verified'),
            ('00000000-0000-0000-0000-00000000bb02',
             '00000000-0000-0000-0000-00000000aa02',
             '00000000-0000-0000-0000-00000000ff01',
             50000, 'opening-sample-aa02', NULL, 'verified')
        """
    )
    op.execute(
        """
        INSERT INTO bids
            (id, project_id, user_id, payment_intent_id, razorpay_payment_id,
             amount_paise, bidder_label, is_mock)
        VALUES
            ('00000000-0000-0000-0000-00000000cc01',
             '00000000-0000-0000-0000-00000000aa01',
             '00000000-0000-0000-0000-00000000ff01',
             '00000000-0000-0000-0000-00000000bb01',
             'mock_00000000-0000-0000-0000-00000000bb01',
             50000, 'Sample entry', TRUE),
            ('00000000-0000-0000-0000-00000000cc02',
             '00000000-0000-0000-0000-00000000aa02',
             '00000000-0000-0000-0000-00000000ff01',
             '00000000-0000-0000-0000-00000000bb02',
             'mock_00000000-0000-0000-0000-00000000bb02',
             50000, 'Sample entry', TRUE)
        """
    )


def downgrade() -> None:
    # Column drops only - the wiped demo rows are not recoverable (they were
    # seeded demo data; see the module docstring).
    op.execute("ALTER TABLE projects DROP CONSTRAINT IF EXISTS ck_projects_property_type")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS is_sample")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS amenities")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS unit_sizes")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS property_type")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS logo_url")
