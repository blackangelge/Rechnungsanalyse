"""
Modell-Paket — importiert alle ORM-Modelle, damit Alembic sie erkennt.

Alembic scannt Base.metadata, um Migrationen zu generieren.
Dafür müssen alle Modell-Klassen importiert worden sein, bevor Alembic
Base.metadata ausliest. Dieser zentrale Import stellt das sicher.
"""

from app.models.ai_config import AIConfig  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.image_settings import ImageSettings  # noqa: F401
from app.models.import_batch import ImportBatch  # noqa: F401
from app.models.invoice_extraction import InvoiceExtraction  # noqa: F401
from app.models.item import Item  # noqa: F401
from app.models.order_position import OrderPosition  # noqa: F401
from app.models.supplier import Supplier  # noqa: F401
from app.models.system_prompt import SystemPrompt  # noqa: F401
