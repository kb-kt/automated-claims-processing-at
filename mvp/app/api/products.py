from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, Request
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    Request = Any  # type: ignore[misc,assignment]

from ai_agent_template.developer_kit.sdk.claim_agent_sdk import ProductCatalogRegistry


router = APIRouter(prefix="/products", tags=["products"]) if APIRouter else None


if router is not None:

    @router.get("")
    def list_products(request: Request) -> dict[str, Any]:
        return _registry(request).list_products()

    @router.get("/{product_id}")
    def get_product(product_id: str, request: Request) -> dict[str, Any]:
        return _registry(request).get_product(product_id)

    @router.get("/{product_id}/policies")
    def list_product_policies(product_id: str, request: Request) -> dict[str, Any]:
        return _registry(request).list_policies(product_id)


def _registry(request: Request) -> ProductCatalogRegistry:
    return ProductCatalogRegistry.from_generated_dir(
        request.app.state.container.settings.fraud_generated_dir
    )
