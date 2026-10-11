"""Modelos Pydantic y entidades del Servicio C4."""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class EstadoPedido(str, Enum):
    CREADO = "Creado"
    PENDIENTE = "Pendiente"
    LISTO = "Listo para despacho"
    ASIGNADO = "Asignado"
    EN_RUTA = "En ruta"
    ENTREGADO = "Entregado"
    FALLIDO = "Fallido"
    CANCELADO = "Cancelado"


class ItemSolicitud(BaseModel):
    medicamento_id: str = Field(min_length=1)
    cantidad: int = Field(gt=0)


class SolicitudPedido(BaseModel):
    solicitud_id: str = Field(min_length=1, description="Clave de idempotencia suministrada por C1")
    documento: str = Field(min_length=1)
    formula: str = Field(min_length=1)
    items: list[ItemSolicitud] = Field(min_length=1)
    direccion: str = Field(min_length=1)
    franja: str = Field(min_length=1)
    consentimiento: bool


class ItemPedido(ItemSolicitud):
    disponible: bool


class Pedido(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    pedido_id: str
    solicitud_id: str
    tipo: str  # "inmediato" o "pendiente"
    items: list[ItemPedido]
    direccion: str
    franja: str
    estado: EstadoPedido
    registrado_en: datetime
    fecha_limite: Optional[datetime] = None
    documento: str
    formula: str
    consentimiento: bool


class EventoEstado(BaseModel):
    pedido_id: str
    nuevo_estado: EstadoPedido
    actor: str = Field(min_length=1)
    detalle: Optional[str] = None


class ConfirmacionAlistamiento(BaseModel):
    actor: str = Field(min_length=1)


class PedidoCreado(BaseModel):
    solicitud_id: str
    pedidos: list[Pedido]
    idempotente: bool = False
