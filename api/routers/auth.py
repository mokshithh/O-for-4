from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import get_current_user, get_supabase_admin
from core.config import settings
from schemas.auth import SignupRequest, LoginRequest, TokenResponse, UserProfile
from models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=201)
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    try:
        client = get_supabase_admin()
        res = client.auth.admin.create_user({
            "email": body.email,
            "password": body.password,
            "email_confirm": True,
            "user_metadata": {"display_name": body.display_name or ""},
        })
        if not res.user:
            raise HTTPException(status_code=400, detail="Signup failed")

        # Sign in immediately to get a session token
        session_res = client.auth.sign_in_with_password({"email": body.email, "password": body.password})
        if not session_res.session:
            raise HTTPException(status_code=400, detail="Signup succeeded but login failed")

        uid = res.user.id
        user = db.query(User).filter(User.id == uid).first()
        if not user:
            user = User(id=uid, email=body.email, hashed_password="supabase_managed", display_name=body.display_name)
            db.add(user)
            db.commit()
            db.refresh(user)

        return TokenResponse(
            access_token=session_res.session.access_token,
            user_id=uid,
            email=body.email,
            display_name=body.display_name,
        )
    except HTTPException:
        raise
    except Exception as exc:
        msg = str(exc)
        if "already registered" in msg.lower() or "already been registered" in msg.lower():
            raise HTTPException(status_code=400, detail="Email already registered")
        raise HTTPException(status_code=400, detail=msg)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    try:
        client = get_supabase_admin()
        res = client.auth.sign_in_with_password({"email": body.email, "password": body.password})
        if not res.session:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        return TokenResponse(
            access_token=res.session.access_token,
            user_id=res.user.id,
            email=res.user.email,
            display_name=res.user.user_metadata.get("display_name"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid email or password")


@router.get("/me", response_model=UserProfile)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
