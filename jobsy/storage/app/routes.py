"""Storage service API routes for file upload, presigned URLs, and deletion."""

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field

from app.s3 import (
    ALLOWED_DOC_TYPES,
    ALLOWED_IMAGE_TYPES,
    create_thumbnail,
    delete_file,
    generate_presigned_url,
    upload_file,
)

router = APIRouter(tags=["storage"])

ALLOWED_FOLDERS = {"avatars", "listings", "chat", "documents"}


def _get_user_id(request: Request) -> str:
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing user context")
    return user_id


@router.post("/upload")
async def upload(
    request: Request,
    file: UploadFile = File(...),
    folder: str = Query(default="listings", description="Target folder"),
):
    """Upload a file. Supports images (JPEG, PNG, WebP) and PDFs.

    For images, automatically generates a thumbnail variant.
    """
    _get_user_id(request)

    if folder not in ALLOWED_FOLDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid folder. Must be one of: {', '.join(ALLOWED_FOLDERS)}",
        )

    content_type = file.content_type or "application/octet-stream"
    allowed = ALLOWED_IMAGE_TYPES | ALLOWED_DOC_TYPES
    if content_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {content_type}",
        )

    file_data = await file.read()

    try:
        result = upload_file(file_data, content_type, folder)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Generate thumbnail for images
    thumbnail_url = None
    if content_type in ALLOWED_IMAGE_TYPES:
        try:
            thumb_data = create_thumbnail(file_data, content_type)
            thumb_result = upload_file(
                thumb_data, content_type, f"{folder}/thumbs"
            )
            thumbnail_url = thumb_result["url"]
        except Exception:
            pass  # Thumbnail generation failure is non-fatal

    return {
        **result,
        "thumbnail_url": thumbnail_url,
    }


class PresignedRequest(BaseModel):
    folder: str = Field(..., description="Target folder")
    content_type: str = Field(..., description="MIME type of the file to upload")


@router.post("/presigned")
async def get_presigned_url(data: PresignedRequest, request: Request):
    """Get a presigned URL for direct client-to-S3 upload.

    Useful for large files where you want to bypass the server.
    """
    _get_user_id(request)

    if data.folder not in ALLOWED_FOLDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid folder. Must be one of: {', '.join(ALLOWED_FOLDERS)}",
        )

    allowed = ALLOWED_IMAGE_TYPES | ALLOWED_DOC_TYPES
    if data.content_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {data.content_type}",
        )

    return generate_presigned_url(data.folder, data.content_type)


@router.delete("/{key:path}")
async def remove_file(key: str, request: Request):
    """Delete a stored file by its key."""
    _get_user_id(request)

    if not delete_file(key):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete file")

    return {"status": "deleted", "key": key}
