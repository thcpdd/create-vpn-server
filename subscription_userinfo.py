import os
import subprocess


def default_hook():
    if not os.path.exists("subinfo"):
        return ""
    
    try:
        result = subprocess.run(
            ['./subinfo'], 
            capture_output=True, 
            text=True
        )
        return result.stdout.strip()
    except Exception:
        return ""


def custom_hook() -> str:
    """
    自定义获取流量信息逻辑

    最终需要返回："upload=1234; download=2234; total=1024000; expire=2218532293"
    流量信息(单位: 字节)、到期信息(时间戳)
    """

    return ""


def get_subscription_userinfo():
    res = custom_hook()
    if res:
        return res
    return default_hook()
