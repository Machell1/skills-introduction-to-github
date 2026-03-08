"""Reverse proxy routes to internal microservices."""

import httpx
from fastapi import APIRouter, Depends, Request, Response

from app.config import SERVICE_URLS
from app.deps import get_current_user

router = APIRouter(prefix="/api", tags=["proxy"])


async def _proxy_request(service: str, path: str, request: Request, user: dict) -> Response:
    """Forward a request to an internal service with user context."""
    base_url = SERVICE_URLS.get(service)
    if not base_url:
        return Response(status_code=404, content=f"Service {service} not found")

    url = f"{base_url}{path}"
    headers = {
        "X-User-ID": user["user_id"],
        "X-User-Role": user["role"],
        "Content-Type": request.headers.get("content-type", "application/json"),
    }

    body = await request.body()

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=body,
            params=dict(request.query_params),
        )

    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=dict(response.headers),
    )


@router.api_route("/profiles/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_profiles(path: str, request: Request, user: dict = Depends(get_current_user)):
    return await _proxy_request("profiles", f"/{path}", request, user)


@router.api_route("/listings/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_listings(path: str, request: Request, user: dict = Depends(get_current_user)):
    return await _proxy_request("listings", f"/{path}", request, user)


@router.api_route("/swipes/{path:path}", methods=["GET", "POST"])
async def proxy_swipes(path: str, request: Request, user: dict = Depends(get_current_user)):
    return await _proxy_request("swipes", f"/{path}", request, user)


@router.api_route("/matches/{path:path}", methods=["GET", "PUT"])
async def proxy_matches(path: str, request: Request, user: dict = Depends(get_current_user)):
    return await _proxy_request("matches", f"/{path}", request, user)


@router.api_route("/geo/{path:path}", methods=["GET"])
async def proxy_geo(path: str, request: Request, user: dict = Depends(get_current_user)):
    return await _proxy_request("geo", f"/{path}", request, user)


@router.api_route("/recommendations/{path:path}", methods=["GET", "POST", "PUT"])
async def proxy_recommendations(path: str, request: Request, user: dict = Depends(get_current_user)):
    return await _proxy_request("recommendations", f"/{path}", request, user)


@router.api_route("/chat/{path:path}", methods=["GET", "POST", "PUT"])
async def proxy_chat(path: str, request: Request, user: dict = Depends(get_current_user)):
    return await _proxy_request("chat", f"/{path}", request, user)


@router.api_route("/notifications/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_notifications(path: str, request: Request, user: dict = Depends(get_current_user)):
    return await _proxy_request("notifications", f"/{path}", request, user)


@router.api_route("/storage/{path:path}", methods=["GET", "POST", "DELETE"])
async def proxy_storage(path: str, request: Request, user: dict = Depends(get_current_user)):
    return await _proxy_request("storage", f"/{path}", request, user)


@router.api_route("/ads/{path:path}", methods=["GET", "POST"])
async def proxy_ads(path: str, request: Request, user: dict = Depends(get_current_user)):
    return await _proxy_request("ads", f"/{path}", request, user)
