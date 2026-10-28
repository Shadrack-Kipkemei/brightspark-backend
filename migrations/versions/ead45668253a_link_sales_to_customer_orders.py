
"""Link sales to customer orders

Revision ID: ead45668253a
Revises: 05aed04e60c3
Create Date: 2026-10-28 18:16:58.227636
"""

from alembic import op
import sqlalchemy as sa


revision = "ead45668253a"
down_revision = "05aed04e60c3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("sales") as batch_op:
        batch_op.add_column(
            sa.Column(
                "customer_order_id",
                sa.String(length=36),
                nullable=True,
            )
        )

        batch_op.create_index(
            "ix_sales_customer_order_id",
            ["customer_order_id"],
            unique=True,
        )

        batch_op.create_foreign_key(
            "fk_sales_customer_order_id_customer_orders",
            "customer_orders",
            ["customer_order_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("sales") as batch_op:
        batch_op.drop_constraint(
            "fk_sales_customer_order_id_customer_orders",
            type_="foreignkey",
        )

        batch_op.drop_index("ix_sales_customer_order_id")

        batch_op.drop_column("customer_order_id")
