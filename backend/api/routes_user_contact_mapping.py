"""
User-Contact Mapping API Routes
Manages the mapping between RBAC users and contacts for identity resolution.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List

from db import get_db
from auth_dependencies import get_current_user_required, get_tenant_context, TenantContext, require_permission
from models_rbac import User, UserRole
from models import UserContactMapping, Contact

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================

class UserContactMappingResponse(BaseModel):
    user_id: int
    contact_id: int
    contact_name: str
    contact_phone: Optional[str] = None
    contact_whatsapp_id: Optional[str] = None
    created_at: str


class CreateUserContactMappingRequest(BaseModel):
    contact_id: int = Field(..., description="Contact ID to map to current user")


class UserContactMappingStatusResponse(BaseModel):
    has_mapping: bool
    mapping: Optional[UserContactMappingResponse] = None


# ============================================================================
# User-Contact Mapping Endpoints
# ============================================================================

@router.get("/api/user-contact-mappings", response_model=List[UserContactMappingResponse])
async def get_all_user_contact_mappings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.read")),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get all user-contact mappings for the tenant (admin-only).
    Used by the Graph View to show user-contact relationships.
    """
    try:
        # Get all users in the tenant
        tenant_user_ids = db.query(UserRole.user_id).filter(
            UserRole.tenant_id == tenant_ctx.tenant_id
        ).distinct().all()
        user_ids = [u[0] for u in tenant_user_ids]

        if not user_ids:
            return []

        # Get all mappings for these users
        mappings = db.query(UserContactMapping).filter(
            UserContactMapping.user_id.in_(user_ids)
        ).all()

        if not mappings:
            return []

        # Get all contacts for these mappings with tenant isolation
        contact_ids = [m.contact_id for m in mappings]
        contact_query = tenant_ctx.filter_by_tenant(
            db.query(Contact), Contact.tenant_id
        )
        contacts = contact_query.filter(Contact.id.in_(contact_ids)).all()
        contacts_by_id = {c.id: c for c in contacts}

        # Build response
        result = []
        for mapping in mappings:
            contact = contacts_by_id.get(mapping.contact_id)
            if contact:  # Only include if contact is accessible
                result.append(UserContactMappingResponse(
                    user_id=mapping.user_id,
                    contact_id=mapping.contact_id,
                    contact_name=contact.friendly_name,
                    contact_phone=contact.phone_number,
                    contact_whatsapp_id=contact.whatsapp_id,
                    created_at=mapping.created_at.isoformat()
                ))

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch user-contact mappings: {str(e)}")


@router.get("/api/user-contact-mapping", response_model=UserContactMappingStatusResponse)
async def get_user_contact_mapping(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get the contact mapping for the current authenticated user.
    Returns the mapping if exists, otherwise indicates no mapping.
    """
    try:
        # Check if user has a contact mapping
        mapping = db.query(UserContactMapping).filter(
            UserContactMapping.user_id == current_user.id
        ).first()

        if not mapping:
            return UserContactMappingStatusResponse(
                has_mapping=False,
                mapping=None
            )

        # MED-008 Security Fix: Get contact with tenant isolation
        contact_query = tenant_ctx.filter_by_tenant(
            db.query(Contact), Contact.tenant_id
        )
        contact = contact_query.filter(Contact.id == mapping.contact_id).first()
        if not contact:
            # Mapping exists but contact not accessible (different tenant or deleted)
            return UserContactMappingStatusResponse(
                has_mapping=False,
                mapping=None
            )

        return UserContactMappingStatusResponse(
            has_mapping=True,
            mapping=UserContactMappingResponse(
                user_id=mapping.user_id,
                contact_id=mapping.contact_id,
                contact_name=contact.friendly_name,
                contact_phone=contact.phone_number,
                contact_whatsapp_id=contact.whatsapp_id,
                created_at=mapping.created_at.isoformat()
            )
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch user-contact mapping: {str(e)}")


@router.post("/api/user-contact-mapping", response_model=UserContactMappingResponse)
async def create_or_update_user_contact_mapping(
    request: CreateUserContactMappingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Create or update the contact mapping for the current authenticated user.
    If a mapping already exists, it will be updated to the new contact.
    """
    try:
        # MED-008 Security Fix: Verify contact exists AND belongs to user's tenant
        contact_query = tenant_ctx.filter_by_tenant(
            db.query(Contact), Contact.tenant_id
        )
        contact = contact_query.filter(Contact.id == request.contact_id).first()
        if not contact:
            # Generic message to prevent contact ID enumeration
            raise HTTPException(status_code=404, detail="Contact not found")

        # Check if user already has a mapping
        existing_mapping = db.query(UserContactMapping).filter(
            UserContactMapping.user_id == current_user.id
        ).first()

        if existing_mapping:
            # Update existing mapping
            existing_mapping.contact_id = request.contact_id
            db.commit()
            db.refresh(existing_mapping)

            return UserContactMappingResponse(
                user_id=existing_mapping.user_id,
                contact_id=existing_mapping.contact_id,
                contact_name=contact.friendly_name,
                contact_phone=contact.phone_number,
                contact_whatsapp_id=contact.whatsapp_id,
                created_at=existing_mapping.created_at.isoformat()
            )
        else:
            # Create new mapping
            new_mapping = UserContactMapping(
                user_id=current_user.id,
                contact_id=request.contact_id
            )
            db.add(new_mapping)
            db.commit()
            db.refresh(new_mapping)

            return UserContactMappingResponse(
                user_id=new_mapping.user_id,
                contact_id=new_mapping.contact_id,
                contact_name=contact.friendly_name,
                contact_phone=contact.phone_number,
                contact_whatsapp_id=contact.whatsapp_id,
                created_at=new_mapping.created_at.isoformat()
            )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create/update user-contact mapping: {str(e)}")


@router.delete("/api/user-contact-mapping")
async def delete_user_contact_mapping(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Delete the contact mapping for the current authenticated user.
    """
    try:
        # Find existing mapping
        mapping = db.query(UserContactMapping).filter(
            UserContactMapping.user_id == current_user.id
        ).first()

        if not mapping:
            raise HTTPException(status_code=404, detail="No contact mapping found for current user")

        # Delete mapping
        db.delete(mapping)
        db.commit()

        return {
            "success": True,
            "message": "Contact mapping deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete user-contact mapping: {str(e)}")
