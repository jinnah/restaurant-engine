"""Constraint names must be deterministic before the first real table exists."""

from sqlalchemy import Column, ForeignKey, Integer, MetaData, Table, UniqueConstraint

from app.core.database import NAMING_CONVENTION, Base


def test_declarative_base_uses_the_naming_convention() -> None:
    assert Base.metadata.naming_convention == NAMING_CONVENTION


def test_generated_constraint_names_are_deterministic() -> None:
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    parent = Table("parents", metadata, Column("id", Integer, primary_key=True))
    child = Table(
        "children",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_id", Integer, ForeignKey(parent.c.id)),
        Column("slug", Integer),
        UniqueConstraint("slug"),
    )

    constraint_names = {c.name for c in child.constraints}
    assert "pk_children" in constraint_names
    assert "uq_children_slug" in constraint_names
    assert "fk_children_parent_id_parents" in constraint_names
