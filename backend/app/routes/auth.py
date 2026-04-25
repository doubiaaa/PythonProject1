from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from backend.app.utils.auth import verify_password, create_access_token, get_user, get_password_hash
from backend.app.utils.database import db
from backend.app.utils.config_manager import config_manager

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """用户登录"""
    user = get_user(form_data.username)
    if not user or not verify_password(form_data.password, user['password_hash']):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user['username']}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "user": {"username": user['username'], "role": user['role']}}

@router.post("/register")
async def register(username: str, password: str):
    """用户注册"""
    # 检查用户是否已存在
    existing_user = get_user(username)
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    # 创建新用户
    hashed_password = get_password_hash(password)
    try:
        connection = db.get_mysql_connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
            (username, hashed_password, 'user')
        )
        connection.commit()
        cursor.close()
        return {"message": "注册成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="注册失败")
