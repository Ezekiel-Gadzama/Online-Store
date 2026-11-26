from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import List
from datetime import datetime, timedelta, timezone
from app.database import get_db
from app import models, schemas
from app.auth import (
    get_current_active_user, require_admin,
    create_password_reset_token, get_password_hash, get_business_id
)
from app.services.email_service import EmailService
from app.services.config_validator import ConfigurationError, format_config_error_response
from app.config import settings
from app.staff_roles import (
    apply_permission_locks,
    assert_can_change_permissions,
    assert_actor_can_grant_permissions,
    assert_no_locked_permission_grants,
    assert_store_market_access_grant,
    can_manage_staff_rights,
    can_view_staff_page,
    is_business_admin,
    is_owner,
    normalize_owner_restrictions,
    section_owner_locked,
    business_admin_covers_store,
)

router = APIRouter()


def _staff_member_schema(user: models.User) -> schemas.User:
    permissions = (
        schemas.UserPermissions(**user.permissions) if user.permissions else schemas.UserPermissions()
    )
    locks = normalize_owner_restrictions(getattr(user, "owner_restrictions", None))
    return schemas.User(
        id=user.id,
        email=user.email,
        name=user.name,
        is_admin=user.is_admin,
        is_business_admin=bool(getattr(user, "is_business_admin", False)),
        business_admin_all_stores=bool(getattr(user, "business_admin_all_stores", True)),
        owner_restrictions=schemas.OwnerRestrictions(**locks),
        created_by_id=user.created_by_id,
        permissions=permissions,
        is_active=user.is_active,
        store_market_access=user.store_market_access,
        store_permissions=user.store_permissions if isinstance(user.store_permissions, dict) else {},
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get("/store-access-options")
def store_access_options(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if not can_view_staff_page(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission required: view_staff",
        )
    from app.store_context import get_owner_stores
    from app.marketplace_service import MARKETPLACE_CHOICES

    owner_id = get_business_id(current_user)
    stores = get_owner_stores(db, owner_id)
    return {
        "stores": [{"id": s.id, "name": s.name} for s in stores],
        "marketplaces": sorted(MARKETPLACE_CHOICES),
    }


@router.get("/", response_model=List[schemas.User])
def get_staff(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all staff accounts. Owner, business admin, or view_staff may access."""
    if not can_view_staff_page(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission required: view_staff"
        )

    business_id = get_business_id(current_user)
    staff = db.query(models.User).filter(
        models.User.is_admin == False,
        models.User.created_by_id == business_id,
    ).all()

    return [_staff_member_schema(user) for user in staff]


@router.get("/business-account", response_model=schemas.User)
def get_business_account(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get the business owner account (owner only — used to edit business account)."""
    if not is_owner(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the business owner may view or edit the business account",
        )
    business_id = get_business_id(current_user)
    admin_user = db.query(models.User).filter(
        models.User.id == business_id,
        models.User.is_admin == True
    ).first()
    if not admin_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business account not found")
    permissions = schemas.UserPermissions(**admin_user.permissions) if admin_user.permissions else schemas.UserPermissions()
    return schemas.User(
        id=admin_user.id,
        email=admin_user.email,
        is_admin=admin_user.is_admin,
        created_by_id=admin_user.created_by_id,
        permissions=permissions,
        is_active=admin_user.is_active,
        name=admin_user.name,
        business_name=admin_user.business_name,
        business_username=admin_user.business_username,
        created_at=admin_user.created_at,
        updated_at=admin_user.updated_at
    )


@router.put("/business-account", response_model=schemas.User)
def update_business_account(
    data: schemas.BusinessAccountUpdate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update business owner account. Owner only."""
    if not is_owner(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the business owner may update the business account",
        )
    business_id = get_business_id(current_user)
    admin_user = db.query(models.User).filter(
        models.User.id == business_id,
        models.User.is_admin == True
    ).first()
    if not admin_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business account not found")
    if data.new_email is not None:
        existing_admin = db.query(models.User).filter(
            models.User.email == data.new_email,
            models.User.is_admin == True,
            models.User.id != admin_user.id
        ).first()
        if existing_admin:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        admin_user.email = data.new_email
    if data.new_password:
        admin_user.hashed_password = get_password_hash(data.new_password)
        admin_user.password_reset_token = None
        admin_user.password_reset_token_expires = None
    if data.name is not None:
        admin_user.name = data.name.strip() or None
    if data.business_name is not None:
        admin_user.business_name = data.business_name.strip() or None
    admin_user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(admin_user)
    permissions = schemas.UserPermissions(**admin_user.permissions) if admin_user.permissions else schemas.UserPermissions()
    return schemas.User(
        id=admin_user.id,
        email=admin_user.email,
        is_admin=admin_user.is_admin,
        created_by_id=admin_user.created_by_id,
        permissions=permissions,
        is_active=admin_user.is_active,
        name=admin_user.name,
        business_name=admin_user.business_name,
        business_username=admin_user.business_username,
        created_at=admin_user.created_at,
        updated_at=admin_user.updated_at
    )


@router.post("/", response_model=schemas.StaffCreateResponse)
def create_staff(
    staff_data: schemas.StaffCreate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create staff. Owner or business admin only."""
    if not can_manage_staff_rights(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner or a business admin may create staff",
        )
    
    created_by_id = current_user.id if current_user.is_admin else current_user.created_by_id
    existing_staff = db.query(models.User).filter(
        models.User.email == staff_data.email,
        models.User.created_by_id == created_by_id
    ).first()
    if existing_staff:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered for this business"
        )
    
    # Determine created_by_id
    created_by_id = current_user.id if current_user.is_admin else current_user.created_by_id
    
    from app.staff_defaults import new_staff_fields
    from secrets import token_urlsafe

    if staff_data.password:
        hashed_password = get_password_hash(staff_data.password)
    else:
        hashed_password = get_password_hash(token_urlsafe(32))

    if is_owner(current_user):
        is_ba = staff_data.is_business_admin
        ba_all_stores = staff_data.business_admin_all_stores if is_ba else False
    else:
        is_ba = False
        ba_all_stores = False

    staff_defaults = new_staff_fields(
        db,
        created_by_id,
        is_business_admin=is_ba,
        business_admin_all_stores=ba_all_stores,
    )
    if staff_data.store_market_access is not None:
        staff_defaults["store_market_access"] = staff_data.store_market_access.model_dump()

    db_user = models.User(
        email=staff_data.email,
        name=(staff_data.name or "").strip() or None,
        hashed_password=hashed_password,
        is_admin=False,
        is_business_admin=staff_defaults["is_business_admin"],
        business_admin_all_stores=staff_defaults["business_admin_all_stores"],
        owner_restrictions={},
        created_by_id=created_by_id,
        permissions=staff_defaults["permissions"],
        store_market_access=staff_defaults["store_market_access"],
        is_active=True,
    )
    
    db.add(db_user)
    db.flush()
    
    # When no password: set reset token and optionally send email (never block staff creation)
    invitation_email_sent = True  # True if password provided (no email needed)
    if not staff_data.password:
        reset_token = create_password_reset_token(db_user.id)
        db_user.password_reset_token = reset_token
        db_user.password_reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=24)

        invitation_email_sent = False
        try:
            business_id = get_business_id(current_user)
            email_service = EmailService(business_id=business_id, db=db)
            reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
            email_body = f"""
            You have been invited to join Online Store.

            Click the following link to set your password and activate your account:
            {reset_url}

            This link will expire in 24 hours.

            If you did not expect this invitation, please contact your administrator.
            """
            result = email_service.send_email(
                to_email=db_user.email,
                subject="Welcome to Online Store - Set Your Password",
                body=email_body
            )
            if result.get("success"):
                invitation_email_sent = True
                print(f"[Staff] Invitation email sent to {db_user.email}")
            else:
                print(f"[Staff] Invitation email not sent: {result.get('message', 'unknown')}")
        except ConfigurationError as e:
            print(f"[Staff] SMTP not configured - invitation email skipped: {e}")
        except Exception as e:
            print(f"[Staff] Failed to send invitation email: {e}")

    db.commit()
    db.refresh(db_user)

    return schemas.StaffCreateResponse(
        user=_staff_member_schema(db_user),
        invitation_email_sent=invitation_email_sent,
    )


@router.put("/{staff_id}", response_model=schemas.User)
def update_staff(
    staff_id: int,
    staff_update: schemas.UserUpdate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update staff. Permission changes: owner or business admin. Owner-only locks and admin role."""
    if not can_view_staff_page(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission required: view_staff",
        )

    staff_user = db.query(models.User).filter(models.User.id == staff_id).first()
    if not staff_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff user not found",
        )

    if staff_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot update owner accounts",
        )

    business_id = get_business_id(current_user)
    if staff_user.created_by_id != business_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff member does not belong to this business",
        )

    editing_self = current_user.id == staff_user.id

    if staff_update.owner_restrictions is not None:
        if not is_owner(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the owner may set owner restrictions",
            )
        staff_user.owner_restrictions = normalize_owner_restrictions(
            staff_update.owner_restrictions.model_dump()
        )
        flag_modified(staff_user, "owner_restrictions")

    if staff_update.is_business_admin is not None or staff_update.business_admin_all_stores is not None:
        if not is_owner(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the owner may change the business admin role",
            )
        if staff_update.is_business_admin is not None:
            staff_user.is_business_admin = staff_update.is_business_admin
        if staff_update.business_admin_all_stores is not None:
            staff_user.business_admin_all_stores = staff_update.business_admin_all_stores

    if staff_update.permissions is not None:
        assert_can_change_permissions(current_user, staff_user)
        if not staff_update.apply_permissions_to_all_stores:
            sid = staff_update.permissions_store_id
            if (
                not is_owner(current_user)
                and is_business_admin(current_user)
                and sid is not None
                and not business_admin_covers_store(current_user, sid)
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You may not set permissions for stores outside your admin scope",
                )
        raw_perm = staff_update.permissions.model_dump()
        perm_store_id = None if staff_update.apply_permissions_to_all_stores else staff_update.permissions_store_id
        assert_actor_can_grant_permissions(current_user, raw_perm, perm_store_id)
        perm = apply_permission_locks(staff_user, raw_perm)
        assert_no_locked_permission_grants(staff_user, raw_perm)
        if staff_update.apply_permissions_to_all_stores:
            staff_user.permissions = perm
            staff_user.store_permissions = {}
            flag_modified(staff_user, "permissions")
            flag_modified(staff_user, "store_permissions")
        else:
            sid = staff_update.permissions_store_id
            if sid is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="permissions_store_id is required when not applying to all stores",
                )
            by_store = dict(staff_user.store_permissions or {})
            by_store[str(sid)] = perm
            staff_user.store_permissions = by_store
            flag_modified(staff_user, "store_permissions")

    rights_manager = can_manage_staff_rights(current_user)

    if staff_update.is_active is not None:
        if not rights_manager and not editing_self:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot change active status")
        if editing_self and not is_owner(current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot change your own active status")
        staff_user.is_active = staff_update.is_active

    if staff_update.new_password:
        if section_owner_locked(staff_user, "password_change") and not is_owner(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Password changes are owner-restricted for this staff member",
            )
        if editing_self and not is_owner(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Use profile settings to change your own password",
            )
        if not is_owner(current_user) and not rights_manager:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot set password")
        staff_user.hashed_password = get_password_hash(staff_update.new_password)
        staff_user.password_reset_token = None
        staff_user.password_reset_token_expires = None

    if staff_update.name is not None:
        staff_user.name = (staff_update.name or "").strip() or None

    if staff_update.store_market_access is not None:
        if section_owner_locked(staff_user, "store_market_access") and not is_owner(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Store access is owner-restricted for this staff member",
            )
        if editing_self and not is_owner(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot change your own store and marketplace access",
            )
        if not is_owner(current_user) and not rights_manager:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot change store access")
        proposed_access = staff_update.store_market_access.model_dump()
        assert_store_market_access_grant(current_user, proposed_access)
        staff_user.store_market_access = proposed_access
        flag_modified(staff_user, "store_market_access")

    staff_user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(staff_user)

    return _staff_member_schema(staff_user)


@router.delete("/{staff_id}")
def delete_staff(
    staff_id: int,
    current_user: models.User = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """Delete a staff account. Only admin can delete staff."""
    staff_user = db.query(models.User).filter(models.User.id == staff_id).first()
    if not staff_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff user not found"
        )
    
    # Cannot delete admin accounts
    if staff_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete admin accounts"
        )
    
    db.delete(staff_user)
    db.commit()
    
    return {"message": "Staff account deleted successfully"}


@router.post("/{staff_id}/resend-password-reset")
def resend_password_reset(
    staff_id: int,
    current_user: models.User = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """Resend password reset link to a staff member. Only admin can do this."""
    staff = db.query(models.User).filter(models.User.id == staff_id).first()
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff user not found"
        )
    
    # Prevent resetting admin passwords
    if staff.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reset password for admin accounts. Use the forgot password feature instead."
        )
    
    # Generate reset token
    reset_token = create_password_reset_token(staff.id)
    
    # Store token in database
    staff.password_reset_token = reset_token
    staff.password_reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=24)
    db.commit()
    
    # Send email with reset link
    try:
        business_id = get_business_id(current_user)
        email_service = EmailService(business_id=business_id, db=db)
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        email_body = f"""
        <html>
        <body>
            <h2>Password Reset Request</h2>
            <p>Your administrator has requested a password reset for your account.</p>
            <p>Click the following link to set your password:</p>
            <p><a href="{reset_url}">{reset_url}</a></p>
            <p>This link will expire in 24 hours.</p>
            <p>If you did not request this, please contact your administrator.</p>
        </body>
        </html>
        """
        
        result = email_service.send_email(
            to_email=staff.email,
            subject="Password Reset Request - Staff Account",
            body=email_body
        )
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Failed to send password reset email. Check SMTP settings and server network (e.g. firewall allows outbound port 587).")
            )
    except HTTPException:
        raise
    except ConfigurationError as e:
        error_detail = format_config_error_response(e)
        error_detail["action_required"] = "Please configure your email settings (SMTP) in the Settings page to send password reset emails."
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail
        )
    except Exception as e:
        print(f"Error sending password reset email: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send password reset email: {str(e)}"
        )
    
    return {"message": "Password reset link has been sent to the staff member's email"}
