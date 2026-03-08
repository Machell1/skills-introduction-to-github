"""Admin service dependencies -- admin role enforcement."""

from fastapi import HTTPException, Request, status


def require_admin(request: Request) -> str:
    """Verify the request comes from an admin user.

    The gateway sets X-User-Role based on the JWT claims.
    """
    user_id = request.headers.get("X-User-ID")
    role = request.headers.get("X-User-Role", "")

    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    if role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    return user_id
