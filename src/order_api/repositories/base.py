import uuid
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from order_api.core.exceptions import AppError
from order_api.schemas.pagination import ListQuery

ModelT = TypeVar("ModelT")


@dataclass
class PageResult(Generic[ModelT]):
    items: list[ModelT]
    page: int
    page_size: int
    total: int
    pages: int


class TenantRepository(Generic[ModelT]):
    def __init__(
        self,
        model: type[ModelT],
        *,
        sortable: dict[str, Any],
        searchable: tuple[Any, ...] = (),
        status_column: Any | None = None,
        eager_options: tuple[Any, ...] = (),
    ) -> None:
        self.model = model
        self.sortable = sortable
        self.searchable = searchable
        self.status_column = status_column
        self.eager_options = eager_options

    def scoped(self, organization_id: uuid.UUID) -> Select:
        stmt = select(self.model).where(self.model.organization_id == organization_id)
        for option in self.eager_options:
            stmt = stmt.options(option)
        return stmt

    def get(self, db: Session, object_id: uuid.UUID, organization_id: uuid.UUID) -> ModelT | None:
        return db.scalar(
            self.scoped(organization_id).where(self.model.id == object_id)  # type: ignore[attr-defined]
        )

    def add(self, db: Session, obj: ModelT) -> ModelT:
        db.add(obj)
        return obj

    def delete(self, db: Session, obj: ModelT) -> None:
        db.delete(obj)

    def list(self, db: Session, organization_id: uuid.UUID, query: ListQuery) -> PageResult[ModelT]:
        stmt = self.scoped(organization_id)
        if query.search and self.searchable:
            pattern = f"%{query.search}%"
            stmt = stmt.where(or_(*(column.ilike(pattern) for column in self.searchable)))
        if query.status is not None:
            if self.status_column is None:
                raise AppError(
                    "VALIDATION_ERROR",
                    "The status filter is not supported for this resource.",
                    status_code=422,
                )
            stmt = stmt.where(self.status_column == query.status)
        if query.created_from:
            stmt = stmt.where(self.model.created_at >= query.created_from)  # type: ignore[attr-defined]
        if query.created_to:
            stmt = stmt.where(self.model.created_at <= query.created_to)  # type: ignore[attr-defined]
        descending = query.sort.startswith("-")
        sort_name = query.sort.removeprefix("-")
        sort_column = self.sortable.get(sort_name)
        if sort_column is None:
            raise AppError(
                "VALIDATION_ERROR",
                f"Unsupported sort field '{sort_name}'.",
                status_code=422,
                details={"allowed": sorted(self.sortable)},
            )
        filtered = stmt.order_by(None)
        total = db.scalar(select(func.count()).select_from(filtered.subquery())) or 0
        order_expression = sort_column.desc() if descending else sort_column.asc()
        items = db.scalars(
            stmt.order_by(order_expression, self.model.id.asc())  # type: ignore[attr-defined]
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        ).all()
        pages = (total + query.page_size - 1) // query.page_size
        return PageResult(list(items), query.page, query.page_size, total, pages)
