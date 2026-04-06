"""
CRUD-Paket — exportiert alle CRUD-Module für einfachen Import in Routen.

Verwendung in Routen:
    from app import crud
    crud.ai_config.get_all(db)
    crud.import_batch.create(db, data, ...)
"""

from app.crud import ai_config  # noqa: F401
from app.crud import document  # noqa: F401
from app.crud import image_settings  # noqa: F401
from app.crud import import_batch  # noqa: F401
from app.crud import item  # noqa: F401
from app.crud import supplier  # noqa: F401
from app.crud import system_prompt  # noqa: F401
