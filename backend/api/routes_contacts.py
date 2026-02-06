from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import sys
import os
import logging
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Contact, UserContactMapping, ContactChannelMapping
from models_rbac import User
from auth_dependencies import TenantContext, get_tenant_context, require_permission
from services.contact_channel_mapping_service import ContactChannelMappingService

logger = logging.getLogger(__name__)

router = APIRouter()


def trigger_whatsapp_resolution(contact_id: int, tenant_id: str):
    """
    Trigger background WhatsApp ID resolution for a contact.

    This function fires-and-forgets a background task to resolve
    the contact's phone number to a WhatsApp ID.
    """
    async def _resolve_async():
        from sqlalchemy.orm import sessionmaker
        from services.whatsapp_proactive_resolver import WhatsAppProactiveResolver

        # Create a new session for the background task
        SessionLocal = sessionmaker(bind=_engine)
        db = SessionLocal()
        try:
            resolver = WhatsAppProactiveResolver(db)
            result = await resolver.resolve_contact(contact_id, tenant_id)
            if result:
                logger.info(f"✅ Background resolution completed for contact {contact_id}: {result}")
            else:
                logger.debug(f"Background resolution: no WhatsApp ID found for contact {contact_id}")
            await resolver.close()
        except Exception as e:
            logger.error(f"Background WhatsApp resolution failed for contact {contact_id}: {e}")
        finally:
            db.close()

    # Run in background without blocking
    try:
        loop = asyncio.get_running_loop()
        asyncio.create_task(_resolve_async())
    except RuntimeError:
        # No event loop running, create one in a thread
        import threading
        def run_in_thread():
            asyncio.run(_resolve_async())
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()

# Global engine reference (set by main routes.py)
_engine = None

def set_engine(engine):
    """Set the global engine reference"""
    global _engine
    _engine = engine

# Dependency to get database session
def get_db():
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Helper functions for user-contact mapping
def get_linked_user_info(db: Session, contact_id: int) -> dict:
    """Get the linked user info for a contact."""
    mapping = db.query(UserContactMapping).filter(
        UserContactMapping.contact_id == contact_id
    ).first()

    if not mapping:
        return {"linked_user_id": None, "linked_user_email": None, "linked_user_name": None}

    user = db.query(User).filter(User.id == mapping.user_id).first()
    if not user:
        return {"linked_user_id": None, "linked_user_email": None, "linked_user_name": None}

    return {
        "linked_user_id": user.id,
        "linked_user_email": user.email,
        "linked_user_name": user.full_name
    }


def enrich_contact_with_user_info(db: Session, contact: Contact) -> dict:
    """Convert a Contact model to a dict enriched with linked user info and channel mappings."""
    contact_dict = {
        "id": contact.id,
        "friendly_name": contact.friendly_name,
        "whatsapp_id": contact.whatsapp_id,
        "phone_number": contact.phone_number,
        "telegram_id": contact.telegram_id,  # Phase 10.1.1
        "telegram_username": contact.telegram_username,  # Phase 10.1.1
        "role": contact.role,
        "is_active": contact.is_active,
        "is_dm_trigger": contact.is_dm_trigger,
        "notes": contact.notes,
        "created_at": contact.created_at,
        "updated_at": contact.updated_at,
    }
    contact_dict.update(get_linked_user_info(db, contact.id))

    # Phase 10.2: Add channel mappings
    mapping_service = ContactChannelMappingService(db)
    mappings = mapping_service.get_channel_mappings(contact.id)
    contact_dict["channel_mappings"] = [
        {
            "id": m.id,
            "channel_type": m.channel_type,
            "channel_identifier": m.channel_identifier,
            "channel_metadata": m.channel_metadata,
            "created_at": m.created_at,
            "updated_at": m.updated_at
        }
        for m in mappings
    ]

    return contact_dict


def update_user_contact_mapping(db: Session, contact_id: int, user_id: int | None):
    """Create, update, or delete user-contact mapping based on user_id value."""
    existing_mapping = db.query(UserContactMapping).filter(
        UserContactMapping.contact_id == contact_id
    ).first()

    if user_id is None:
        # No change requested
        return

    if user_id == -1:
        # Delete mapping if exists
        if existing_mapping:
            db.delete(existing_mapping)
        return

    # Verify the user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail=f"User with ID {user_id} not found")

    # Check if this user is already mapped to another contact
    existing_user_mapping = db.query(UserContactMapping).filter(
        UserContactMapping.user_id == user_id
    ).first()

    if existing_user_mapping and existing_user_mapping.contact_id != contact_id:
        raise HTTPException(
            status_code=400,
            detail=f"User is already linked to another contact (ID: {existing_user_mapping.contact_id})"
        )

    if existing_mapping:
        # Update existing mapping
        existing_mapping.user_id = user_id
        existing_mapping.updated_at = datetime.utcnow()
    else:
        # Create new mapping
        new_mapping = UserContactMapping(
            user_id=user_id,
            contact_id=contact_id
        )
        db.add(new_mapping)


# Schemas

# Phase 10.2: Channel Mapping Schemas
class ChannelMappingResponse(BaseModel):
    """Response model for a channel mapping."""
    id: int
    channel_type: str
    channel_identifier: str
    channel_metadata: Optional[dict]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChannelMappingCreate(BaseModel):
    """Request model for creating a channel mapping."""
    channel_type: str = Field(..., description="Channel type (whatsapp, telegram, phone, discord, email, etc.)")
    channel_identifier: str = Field(..., description="Channel-specific identifier")
    channel_metadata: Optional[dict] = Field(None, description="Optional metadata (e.g., username)")


class ContactCreate(BaseModel):
    friendly_name: str = Field(..., min_length=1, max_length=100)
    whatsapp_id: str | None = Field(None, max_length=50)
    phone_number: str | None = Field(None, max_length=20)
    telegram_id: str | None = Field(None, max_length=50)  # Phase 10.1.1: Telegram user ID
    telegram_username: str | None = Field(None, max_length=50)  # Phase 10.1.1: Telegram @username
    role: str = Field(default="user", pattern="^(user|agent)$")
    is_dm_trigger: bool = Field(default=True)  # Phase 4.3: Default True, user can opt-out during creation
    notes: str | None = None
    linked_user_id: int | None = Field(None, description="ID of the system user to link this contact to")

    class Config:
        json_schema_extra = {
            "example": {
                "friendly_name": "Alice",
                "whatsapp_id": "123456789012345",
                "phone_number": "5500000000000",
                "telegram_id": "123456789",
                "telegram_username": "alice_user",
                "role": "user",
                "is_dm_trigger": True,
                "notes": "Example contact",
                "linked_user_id": None
            }
        }


class ContactUpdate(BaseModel):
    friendly_name: str | None = Field(None, min_length=1, max_length=100)
    whatsapp_id: str | None = Field(None, max_length=50)
    phone_number: str | None = Field(None, max_length=20)
    telegram_id: str | None = Field(None, max_length=50)  # Phase 10.1.1: Telegram user ID
    telegram_username: str | None = Field(None, max_length=50)  # Phase 10.1.1: Telegram @username
    role: str | None = Field(None, pattern="^(user|agent)$")
    is_active: bool | None = None
    is_dm_trigger: bool | None = None  # Phase 4.3
    notes: str | None = None
    linked_user_id: int | None = Field(None, description="ID of the system user to link this contact to (use -1 to unlink)")


class ContactResponse(BaseModel):
    id: int
    friendly_name: str
    whatsapp_id: str | None
    phone_number: str | None
    telegram_id: str | None  # Phase 10.1.1: Telegram user ID
    telegram_username: str | None  # Phase 10.1.1: Telegram @username
    role: str
    is_active: bool
    is_dm_trigger: bool  # Phase 4.3
    notes: str | None
    created_at: datetime
    updated_at: datetime
    # Linked system user fields
    linked_user_id: int | None = None
    linked_user_email: str | None = None
    linked_user_name: str | None = None
    # Phase 10.2: Channel mappings
    channel_mappings: List[ChannelMappingResponse] = []

    class Config:
        from_attributes = True


# Routes
@router.get("/", response_model=List[ContactResponse])
def list_contacts(
    active_only: bool = False,
    role: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contacts.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """List all contacts with optional filters (requires contacts.read permission)"""

    # Apply tenant filtering
    query = ctx.filter_by_tenant(db.query(Contact), Contact.tenant_id)

    if active_only:
        query = query.filter(Contact.is_active == True)

    if role and role in ["user", "agent"]:
        query = query.filter(Contact.role == role)

    contacts = query.order_by(Contact.friendly_name).all()

    # Enrich contacts with linked user info
    return [enrich_contact_with_user_info(db, contact) for contact in contacts]


@router.get("/{contact_id}", response_model=ContactResponse)
def get_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contacts.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Get a specific contact by ID (requires contacts.read permission)"""
    # Apply tenant filtering to prevent cross-tenant access
    query = ctx.filter_by_tenant(db.query(Contact), Contact.tenant_id)
    contact = query.filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return enrich_contact_with_user_info(db, contact)


@router.post("/", response_model=ContactResponse, status_code=201)
def create_contact(
    contact: ContactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contacts.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Create a new contact (requires contacts.write permission)"""

    # Check if friendly_name already exists (within tenant)
    query = ctx.filter_by_tenant(db.query(Contact), Contact.tenant_id)
    existing = query.filter(Contact.friendly_name == contact.friendly_name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Contact with this friendly name already exists")

    # Check if whatsapp_id already exists (if provided, within tenant)
    if contact.whatsapp_id:
        existing_wa = query.filter(Contact.whatsapp_id == contact.whatsapp_id).first()
        if existing_wa:
            raise HTTPException(status_code=400, detail="Contact with this WhatsApp ID already exists")

    # Phase 10.1.1: Check if telegram_id already exists (if provided, within tenant)
    if contact.telegram_id:
        existing_tg = query.filter(Contact.telegram_id == contact.telegram_id).first()
        if existing_tg:
            raise HTTPException(
                status_code=400,
                detail=f"Contact with Telegram ID {contact.telegram_id} already exists: {existing_tg.friendly_name}"
            )

    # NOTE: Phone number is NOT unique - multiple agents can share the same phone number
    # This allows multiple agent personas (e.g., Assistant, Support) to use the same WhatsApp account

    contact_data = contact.model_dump()

    # Extract linked_user_id before creating the contact (not a column on Contact model)
    linked_user_id = contact_data.pop("linked_user_id", None)

    # Phase 7.6: Assign tenant_id and user_id for multi-tenancy
    contact_data["tenant_id"] = ctx.tenant_id
    contact_data["user_id"] = ctx.user.id

    new_contact = Contact(**contact_data)
    db.add(new_contact)
    db.commit()
    db.refresh(new_contact)

    # Handle user-contact mapping if linked_user_id was provided
    if linked_user_id is not None and linked_user_id > 0:
        update_user_contact_mapping(db, new_contact.id, linked_user_id)
        db.commit()

    # Trigger WhatsApp ID resolution if phone number provided but no WhatsApp ID
    if new_contact.phone_number and not new_contact.whatsapp_id:
        logger.info(f"🔍 Triggering WhatsApp ID resolution for new contact '{new_contact.friendly_name}'")
        trigger_whatsapp_resolution(new_contact.id, ctx.tenant_id)

    return enrich_contact_with_user_info(db, new_contact)


@router.put("/{contact_id}", response_model=ContactResponse)
def update_contact(
    contact_id: int,
    contact: ContactUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contacts.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Update an existing contact (requires contacts.write permission)"""

    # Get contact with tenant filtering
    query = ctx.filter_by_tenant(db.query(Contact), Contact.tenant_id)
    db_contact = query.filter(Contact.id == contact_id).first()
    if not db_contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Verify user can access this contact (tenant isolation)
    if not ctx.can_access_resource(db_contact.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contact")

    # Check for unique constraints
    if contact.friendly_name and contact.friendly_name != db_contact.friendly_name:
        existing = db.query(Contact).filter(
            Contact.friendly_name == contact.friendly_name,
            Contact.id != contact_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Contact with this friendly name already exists")

    if contact.whatsapp_id and contact.whatsapp_id != db_contact.whatsapp_id:
        existing = db.query(Contact).filter(
            Contact.whatsapp_id == contact.whatsapp_id,
            Contact.id != contact_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Contact with this WhatsApp ID already exists")

    # Phase 10.1.1: Check telegram_id uniqueness
    if contact.telegram_id and contact.telegram_id != db_contact.telegram_id:
        existing = db.query(Contact).filter(
            Contact.telegram_id == contact.telegram_id,
            Contact.id != contact_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Contact with this Telegram ID already exists: {existing.friendly_name}"
            )

    # NOTE: Phone number is NOT unique - multiple agents can share the same phone number
    # This allows multiple agent personas (e.g., Assistant, Support) to use the same WhatsApp account

    # Track phone number before update for resolution trigger
    old_phone_number = db_contact.phone_number
    old_whatsapp_id = db_contact.whatsapp_id

    # Update fields (excluding linked_user_id which is handled separately)
    update_data = contact.model_dump(exclude_unset=True)
    linked_user_id = update_data.pop("linked_user_id", None)

    for field, value in update_data.items():
        setattr(db_contact, field, value)

    db_contact.updated_at = datetime.utcnow()

    # Handle user-contact mapping update
    if linked_user_id is not None:
        update_user_contact_mapping(db, contact_id, linked_user_id)

    db.commit()
    db.refresh(db_contact)

    # CRITICAL: Clear contact cache after update (especially for is_dm_trigger changes)
    # This ensures the MessageFilter uses the latest contact settings
    if hasattr(request.app.state, 'contact_service'):
        request.app.state.contact_service.clear_cache()

    # Trigger WhatsApp ID resolution if phone number changed/added and no WhatsApp ID exists
    phone_changed = db_contact.phone_number and db_contact.phone_number != old_phone_number
    no_whatsapp_id = not db_contact.whatsapp_id
    if phone_changed and no_whatsapp_id:
        logger.info(f"🔍 Triggering WhatsApp ID resolution for updated contact '{db_contact.friendly_name}'")
        trigger_whatsapp_resolution(db_contact.id, ctx.tenant_id)

    return enrich_contact_with_user_info(db, db_contact)


@router.delete("/{contact_id}", status_code=204)
def delete_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contacts.delete")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Delete a contact (requires contacts.delete permission)"""

    # Get contact with tenant filtering
    query = ctx.filter_by_tenant(db.query(Contact), Contact.tenant_id)
    contact = query.filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Verify user can access this contact (tenant isolation)
    if not ctx.can_access_resource(contact.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contact")

    # Delete any user-contact mapping first
    existing_mapping = db.query(UserContactMapping).filter(
        UserContactMapping.contact_id == contact_id
    ).first()
    if existing_mapping:
        db.delete(existing_mapping)

    db.delete(contact)
    db.commit()
    return None


@router.get("/lookup/by-identifier")
def lookup_contact(
    identifier: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contacts.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Lookup a contact by any identifier (friendly_name, whatsapp_id, or phone_number).
    Returns the contact if found, or null if not found.

    Requires: contacts.read permission
    Security: HIGH-009 fix - Added auth + tenant isolation (2026-02-02)
    """
    # Apply tenant filter to all queries
    base_query = ctx.filter_by_tenant(db.query(Contact), Contact.tenant_id)

    # Try to find by friendly_name
    contact = base_query.filter(Contact.friendly_name == identifier).first()
    if contact:
        return enrich_contact_with_user_info(db, contact)

    # Try whatsapp_id
    contact = base_query.filter(Contact.whatsapp_id == identifier).first()
    if contact:
        return enrich_contact_with_user_info(db, contact)

    # Try phone_number (normalize by removing + prefix)
    normalized = identifier.lstrip("+")
    contact = base_query.filter(Contact.phone_number == normalized).first()
    if contact:
        return enrich_contact_with_user_info(db, contact)

    # Also try with + prefix for phone
    contact = base_query.filter(Contact.phone_number == f"+{normalized}").first()
    if contact:
        return enrich_contact_with_user_info(db, contact)

    return None


# Phase 10.2: Channel Mapping Endpoints

@router.post("/{contact_id}/channels", response_model=ChannelMappingResponse, status_code=201)
def add_channel_mapping(
    contact_id: int,
    mapping: ChannelMappingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contacts.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Add a new channel mapping to a contact (requires contacts.write permission)"""

    # Verify contact exists and user has access
    query = ctx.filter_by_tenant(db.query(Contact), Contact.tenant_id)
    contact = query.filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    if not ctx.can_access_resource(contact.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contact")

    # Add the mapping
    mapping_service = ContactChannelMappingService(db)
    try:
        new_mapping = mapping_service.add_channel_mapping(
            contact_id=contact_id,
            channel_type=mapping.channel_type,
            channel_identifier=mapping.channel_identifier,
            channel_metadata=mapping.channel_metadata,
            tenant_id=contact.tenant_id or "default"
        )

        # Trigger WhatsApp ID resolution when a phone channel is added
        # and the contact doesn't already have a WhatsApp ID
        if mapping.channel_type == 'phone' and not contact.whatsapp_id:
            logger.info(f"🔍 Triggering WhatsApp ID resolution for contact '{contact.friendly_name}' (new phone mapping)")
            trigger_whatsapp_resolution(contact_id, ctx.tenant_id)

        return new_mapping
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{contact_id}/channels/{mapping_id}", status_code=204)
def remove_channel_mapping(
    contact_id: int,
    mapping_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contacts.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Remove a channel mapping from a contact (requires contacts.write permission)"""

    # Verify contact exists and user has access
    query = ctx.filter_by_tenant(db.query(Contact), Contact.tenant_id)
    contact = query.filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    if not ctx.can_access_resource(contact.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contact")

    # Verify mapping belongs to this contact
    mapping_service = ContactChannelMappingService(db)
    mapping = mapping_service.get_mapping_by_id(mapping_id)
    if not mapping or mapping.contact_id != contact_id:
        raise HTTPException(status_code=404, detail="Channel mapping not found")

    # Remove the mapping
    mapping_service.remove_channel_mapping_by_id(mapping_id)
    return None


@router.put("/{contact_id}/channels/{mapping_id}", response_model=ChannelMappingResponse)
def update_channel_mapping_metadata(
    contact_id: int,
    mapping_id: int,
    metadata: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contacts.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Update metadata for a channel mapping (requires contacts.write permission)"""

    # Verify contact exists and user has access
    query = ctx.filter_by_tenant(db.query(Contact), Contact.tenant_id)
    contact = query.filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    if not ctx.can_access_resource(contact.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contact")

    # Verify mapping belongs to this contact
    mapping_service = ContactChannelMappingService(db)
    mapping = mapping_service.get_mapping_by_id(mapping_id)
    if not mapping or mapping.contact_id != contact_id:
        raise HTTPException(status_code=404, detail="Channel mapping not found")

    # Update the metadata
    updated_mapping = mapping_service.update_channel_metadata(mapping_id, metadata)
    if not updated_mapping:
        raise HTTPException(status_code=404, detail="Failed to update mapping")

    return updated_mapping


# WhatsApp ID Resolution Endpoints

class WhatsAppResolutionResponse(BaseModel):
    """Response model for WhatsApp ID resolution."""
    success: bool
    contact_id: Optional[int] = None
    whatsapp_id: Optional[str] = None
    message: str


class BatchResolutionResponse(BaseModel):
    """Response model for batch WhatsApp ID resolution."""
    success: bool
    resolved: int
    failed: int
    skipped: int
    total: int
    message: Optional[str] = None


@router.post("/{contact_id}/resolve-whatsapp", response_model=WhatsAppResolutionResponse)
async def resolve_contact_whatsapp(
    contact_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contacts.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Resolve WhatsApp ID for a specific contact.

    This endpoint calls the WhatsApp IsOnWhatsApp API to resolve the contact's
    phone number to their WhatsApp ID.

    Args:
        contact_id: Contact ID to resolve
        force: If True, re-resolve even if contact already has a WhatsApp ID

    Returns:
        Resolution result with the WhatsApp ID if found
    """
    from services.whatsapp_proactive_resolver import WhatsAppProactiveResolver

    # Verify contact exists and user has access
    query = ctx.filter_by_tenant(db.query(Contact), Contact.tenant_id)
    contact = query.filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    if not ctx.can_access_resource(contact.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contact")

    # Check if contact has phone number
    if not contact.phone_number:
        return WhatsAppResolutionResponse(
            success=False,
            contact_id=contact_id,
            message="Contact has no phone number to resolve"
        )

    # Check if already resolved (unless force)
    if contact.whatsapp_id and not force:
        return WhatsAppResolutionResponse(
            success=True,
            contact_id=contact_id,
            whatsapp_id=contact.whatsapp_id,
            message="Contact already has WhatsApp ID"
        )

    # Resolve the WhatsApp ID
    resolver = WhatsAppProactiveResolver(db)
    try:
        result = await resolver.resolve_contact(contact_id, ctx.tenant_id, force=force)
        await resolver.close()

        if result:
            # Refresh contact to get updated whatsapp_id
            db.refresh(contact)
            return WhatsAppResolutionResponse(
                success=True,
                contact_id=contact_id,
                whatsapp_id=contact.whatsapp_id,
                message=f"Successfully resolved WhatsApp ID: {contact.whatsapp_id}"
            )
        else:
            return WhatsAppResolutionResponse(
                success=False,
                contact_id=contact_id,
                message="Phone number not registered on WhatsApp or no MCP instance available"
            )
    except Exception as e:
        logger.error(f"WhatsApp resolution failed for contact {contact_id}: {e}")
        return WhatsAppResolutionResponse(
            success=False,
            contact_id=contact_id,
            message=f"Resolution failed: {str(e)}"
        )


@router.post("/resolve-all-whatsapp", response_model=BatchResolutionResponse)
async def resolve_all_contacts_whatsapp(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contacts.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Batch resolve WhatsApp IDs for all contacts with phone numbers but no WhatsApp ID.

    This endpoint processes all contacts in the tenant that have a phone number
    but no WhatsApp ID, resolving them in batches.

    Returns:
        Resolution statistics
    """
    from services.whatsapp_proactive_resolver import WhatsAppProactiveResolver

    resolver = WhatsAppProactiveResolver(db)
    try:
        result = await resolver.resolve_all_contacts(ctx.tenant_id)
        await resolver.close()

        return BatchResolutionResponse(
            success=result.get("success", False),
            resolved=result.get("resolved", 0),
            failed=result.get("failed", 0),
            skipped=result.get("skipped", 0),
            total=result.get("total", 0),
            message=result.get("message") or result.get("error")
        )
    except Exception as e:
        logger.error(f"Batch WhatsApp resolution failed: {e}")
        return BatchResolutionResponse(
            success=False,
            resolved=0,
            failed=0,
            skipped=0,
            total=0,
            message=f"Resolution failed: {str(e)}"
        )
