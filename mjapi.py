import requests
import logging

LOGGER = logging.getLogger(__name__)

def mjapi() -> str:
    url = "https://mjai.7xcnnw11phu.eu.org/user/trial"
    payload = {"code": "FREE_TRIAL_SPONSORED_BY_MJAPI_DiscordID_9ns4esyx"}
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        session_id = response.json().get("id")
        print(session_id)
        LOGGER.info("成功获取 trial session_id: %s", session_id)
        return session_id or ""
    except Exception as e:
        LOGGER.error("mjapi trial 失败: %s", e)
        return ""

# 测试用
if __name__ == "__main__":
    mjapi()