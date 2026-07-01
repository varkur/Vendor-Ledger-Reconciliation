---
inclusion: auto
---

# API Layer Standard — Mandatory Flow

Every API endpoint MUST follow this 4-layer architecture. No exceptions.

## Flow

```
Controller → Service → Repository Interface → Repository Implementation
```

## Layer Responsibilities

### 1. Controller (Thin — API Layer)

**Location:** `src/api/v1/endpoints/<module>/`

```python
@router.get("/items")
async def list_items(
    skip: int = Query(default=0),
    service: ItemService = Depends(_get_item_service),
):
    return await service.list_items(skip=skip)
```

**Rules:**
- Parse HTTP (query params, path params, request body)
- Validate via Pydantic schemas (automatic)
- Map business errors to HTTP status codes (`ValueError → 404/409`)
- Delegate ALL logic to the Service layer
- NEVER import ORM models or SQLAlchemy
- NEVER write SQL or business rules
- Max 5-10 lines per endpoint

---

### 2. Service (Business Logic — Application Layer)

**Location:** `src/application/services/<service_name>.py`

```python
class ItemService:
    def __init__(self, session: AsyncSession, item_repo: IItemRepository) -> None:
        self._session = session
        self._repo = item_repo

    async def create_item(self, request: CreateItemRequest, actor: User) -> ItemResponse:
        if await self._repo.exists_by_code(request.code):
            raise ValueError(f"Item '{request.code}' already exists")
        item = Item(id=uuid4(), ...)
        created = await self._repo.create(item)
        return self._to_response(created)
```

**Rules:**
- Contains ALL business logic and orchestration
- Calls repository methods for data access
- May use session directly for complex aggregation queries
- Raises `ValueError` for business rule violations
- Returns Pydantic response DTOs (not ORM models)
- No HTTP concepts (no Request, no HTTPException)
- Concrete class (no interface needed — only one implementation)

---

### 3. Repository Interface (Port — Domain Layer)

**Location:** `src/domain/repositories/<entity>_repository.py`

**Naming convention:** `I<Entity>Repository`

```python
from abc import ABC, abstractmethod

class IItemRepository(ABC):
    @abstractmethod
    async def get_by_id(self, item_id: UUID) -> Item | None: ...

    @abstractmethod
    async def create(self, item: Item) -> Item: ...

    @abstractmethod
    async def list_all(self, skip: int = 0, limit: int = 100) -> list[Item]: ...
```

**Rules:**
- Uses ABC with `@abstractmethod`
- Lives in `domain/` — no framework imports
- Methods accept/return domain entities only (NOT ORM models)
- Naming: `I` prefix + entity name + `Repository`
- Defines WHAT, not HOW

---

### 4. Repository Implementation (Adapter — Infrastructure Layer)

**Location:** `src/infrastructure/database/repositories/<entity>_repository_impl.py`

```python
class ItemRepositoryImpl(IItemRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, item_id: UUID) -> Item | None:
        stmt = select(ItemModel).where(ItemModel.id == item_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None
```

**Rules:**
- Implements the interface from domain layer
- Contains SQLAlchemy queries
- Maps ORM models ↔ domain entities
- No business logic — pure data access

---

## Dependency Injection (FastAPI)

```python
# In controller file
def _get_item_service(
    session: AsyncSession = Depends(get_db_session),
    item_repo: IItemRepository = Depends(get_item_repository),
) -> ItemService:
    return ItemService(session=session, item_repo=item_repo)
```

---

## File Naming Convention

| Layer | File Pattern | Class Pattern |
|-------|-------------|---------------|
| Controller | `src/api/v1/endpoints/<module>/controller.py` | Functions (routes) |
| Schemas | `src/api/v1/endpoints/<module>/schemas.py` | Pydantic models |
| Service | `src/application/services/<name>_service.py` | `<Name>Service` |
| Interface | `src/domain/repositories/<entity>_repository.py` | `I<Entity>Repository` |
| Implementation | `src/infrastructure/database/repositories/<entity>_repository_impl.py` | `<Entity>RepositoryImpl` |
| ORM Model | `src/infrastructure/database/models/<module>/<entity>_model.py` | `<Entity>Model` |
| Domain Entity | `src/domain/entities/<module>/<entity>.py` | `<Entity>` (dataclass) |

---

## What NEVER belongs in each layer

| Layer | NEVER contains |
|-------|---------------|
| Controller | SQL, business rules, ORM models, direct session queries |
| Service | HTTP concepts, Request/Response objects, HTTPException |
| Repository Interface | SQLAlchemy, framework imports, implementation details |
| Repository Impl | Business logic, HTTP concepts, validation rules |

---

## Error Handling Flow

```
Repository → raises nothing (returns None if not found)
Service    → raises ValueError("User not found")
Controller → catches ValueError → raises HTTPException(404, detail=str(e))
```

---

## Checklist for New Endpoints

Before creating any new API endpoint, verify:

- [ ] Controller is thin (< 10 lines, delegates to service)
- [ ] Service contains all business logic
- [ ] Repository interface defined in `domain/repositories/`
- [ ] Repository implementation in `infrastructure/database/repositories/`
- [ ] Interface uses `I` prefix naming (`IUserRepository`)
- [ ] Service raises `ValueError` for business errors (not HTTPException)
- [ ] Controller maps errors to HTTP status codes
- [ ] No ORM models imported in controller
- [ ] No SQLAlchemy imported in controller
- [ ] Dependency injection via `Depends()` factory function
