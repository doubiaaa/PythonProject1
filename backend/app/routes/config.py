from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.app.utils.config_manager import config_manager
from backend.app.utils.auth import verify_token, get_user

router = APIRouter(prefix="/api/config", tags=["config"])
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    username = verify_token(token)
    if username is None:
        raise HTTPException(status_code=401, detail="无效的认证凭据")
    user = get_user(username)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user

@router.get("/")
async def get_all_configs(current_user: dict = Depends(get_current_user)):
    """获取所有配置"""
    return config_manager.get_all_configs()

@router.get("/{key}")
async def get_config(key: str, current_user: dict = Depends(get_current_user)):
    """获取指定配置"""
    value = config_manager.get_config(key)
    if value is None:
        raise HTTPException(status_code=404, detail="配置不存在")
    return {"key": key, "value": value}

@router.post("/{key}")
async def set_config(key: str, value: str, current_user: dict = Depends(get_current_user)):
    """设置配置"""
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="权限不足")
    success = config_manager.set_config(key, value)
    if not success:
        raise HTTPException(status_code=500, detail="设置配置失败")
    return {"message": "配置设置成功", "key": key, "value": value}
