from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from auth import verify_admin_token
from auth import key_store
from models import APIKeyCreate, APIKeyResponse, APIKeyUpdate

router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/keys", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(payload: APIKeyCreate, _: str = Depends(verify_admin_token)):
    return key_store.create(payload)

@router.get("/keys", response_model=List[APIKeyResponse])
async def list_api_keys(admin: str = Depends(verify_admin_token)):
    return key_store.list_all()

@router.get("/keys/{key}", response_model=APIKeyResponse)
async def get_api_key(key: str, admin: str = Depends(verify_admin_token)):
    data = key_store.get(key)
    if not data:
        raise HTTPException(status_code=404, detail="API key not found")
    return data

@router.patch("/keys/{key}", response_model=APIKeyResponse)
async def update_api_key(key: str, payload: APIKeyUpdate, admin: str = Depends(verify_admin_token)):
    updated = key_store.update(key, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="API key not found")
    return updated

@router.delete("/keys/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(key: str, admin: str = Depends(verify_admin_token)):
    if not key_store.delete(key):
        raise HTTPException(status_code=404, detail="API key not found")
    return None

@router.post("/keys/{key}/rotate", response_model=APIKeyResponse)
async def rotate_api_key(key: str, admin: str = Depends(verify_admin_token)):
    existing = key_store.get(key)
    if not existing:
        raise HTTPException(status_code=404, detail="API key not found")
    puter_token = key_store.get_puter_token(key)
    payload = APIKeyCreate(
        name=existing.name,
        puter_token=puter_token,
        rate_limit_requests=existing.rate_limit_requests,
        rate_limit_tokens=existing.rate_limit_tokens,
    )
    new_key = key_store.create(payload)
    key_store.delete(key)
    return new_key
