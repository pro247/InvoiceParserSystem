from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

# Local imports
from database.db_session import get_db, SessionLocal
from database.models import User
from settings import JWT_SECRET, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

# Password encryption setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Router for authentication endpoints
router = APIRouter(tags=["auth"])

# OAuth2 setup for FastAPI dependency injection
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/signin")


# ------------------------------
# Pydantic Schemas
# ------------------------------
class SignupIn(BaseModel):
    username: str
    email: EmailStr
    password: str


class SignInIn(BaseModel):
    username: Optional[str]
    email: Optional[EmailStr]
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ------------------------------
# Utility functions
# ------------------------------
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt


# ------------------------------
# Routes
# ------------------------------
@router.post("/signup", response_model=Token)
def signup(payload: SignupIn, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter((User.username == payload.username) | (User.email == payload.email)).first()

    if existing_user:
        raise HTTPException(status_code=400, detail="Username or email already registered")

    user = User(username=payload.username, email=payload.email, hashed_password=get_password_hash(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.username, "user_id": user.id})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/signin", response_model=Token)
def signin(payload: SignInIn, db: Session = Depends(get_db)):
    if payload.email:
        user = db.query(User).filter(User.email == payload.email).first()
    else:
        user = db.query(User).filter(User.username == payload.username).first()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": user.username, "user_id": user.id})
    return {"access_token": token, "token_type": "bearer"}


# ------------------------------
# Current user dependency
# ------------------------------
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        user_id: int = payload.get("user_id")

        if username is None or user_id is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception

    return user
