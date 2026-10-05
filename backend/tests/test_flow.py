"""End-to-end flow with a scripted fake LLM: signup -> clarify -> build -> test/repair -> sim -> change -> retest."""
import copy
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["LLM_API_KEY"] = "fake"
os.environ["PUBLIC_URL"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app import agent  # noqa: E402
from app.main import app  # noqa: E402
from app.spec import EXAMPLE_WORKSHOP  # noqa: E402

calls = []


def fake_chat_json(system: str, user: str, temperature: float = 0.2) -> dict:
    has_spec = "Current bot spec (null if no bot yet):\nnull" not in user
    if system.startswith('You are "BotLab"'):
        calls.append("analyze")
        owner_msgs = user.count("OWNER:")
        if not has_spec and owner_msgs == 1:
            return {"intent": "build", "template": "workshop", "ready": False,
                    "questions": ["ظرفیت هر کارگاه چند نفر است؟ (اگر نگویید: ۱۰)"], "requirements": "کارگاه آبرنگ",
                    "reply": "چند سؤال دارم:"}
        if not has_spec:
            return {"intent": "build", "template": "workshop", "ready": True, "questions": [],
                    "requirements": "کارگاه آبرنگ با ظرفیت ۲ نفر", "reply": ""}
        return {"intent": "change", "template": "workshop", "ready": True, "questions": [],
                "requirements": "کارگاه آبرنگ با ظرفیت ۲ نفر و فهرست انتظار", "reply": ""}
    if system.startswith("You convert"):
        calls.append("build")
        spec = copy.deepcopy(EXAMPLE_WORKSHOP)
        spec["workshop"]["sessions"][0]["capacity"] = 2
        change = []
        if "فهرست انتظار" in user:
            spec["workshop"]["waitlist"]["enabled"] = True
            change = ["فهرست انتظار فعال شد"]
        return {"spec": spec, "assumptions": ["لغو ثبت‌نام مجاز است"], "change_summary": change}
    if system.startswith("You are a QA"):
        calls.append("tests")
        if "فهرست انتظار فعال شد" in user:
            return {"tests": [{"name": "انتظار", "steps": [
                {"user": "u1", "send": "📝 آبرنگ مقدماتی"}, {"user": "u1", "send": "علی رضایی"},
                {"user": "u1", "send": "09121234567"}, {"user": "u1", "send": "✅ تأیید"},
                {"user": "u2", "send": "📝 آبرنگ مقدماتی"}, {"user": "u2", "send": "سارا"},
                {"user": "u2", "send": "09121234568"}, {"user": "u2", "send": "✅ تأیید"},
                {"user": "u3", "send": "📝 آبرنگ مقدماتی", "expect": ["⏳ عضویت در فهرست انتظار"]}]}]}
        return {"tests": [
            {"name": "ظرفیت دو نفره", "steps": [{"send": "📅 کارگاه‌ها", "expect": ["ظرفیت باقی‌مانده: 2 از 2"]}]},
            {"name": "آزمون غلط", "steps": [{"send": "📅 کارگاه‌ها", "expect": ["چیزی که وجود ندارد"]}]},
        ]}
    if system.startswith("You are debugging"):
        calls.append("repair")
        return {"diagnosis": "انتظار آزمون اشتباه بود", "spec": None, "tests": [], "drop": ["آزمون غلط"]}
    raise AssertionError("unexpected prompt")


agent.chat_json = fake_chat_json


def wait_idle(c, h, bot_id):
    for _ in range(100):
        r = c.get(f"/api/bots/{bot_id}/messages", headers=h).json()
        if r["agent_status"] == "idle":
            return r["messages"]
        time.sleep(0.1)
    raise AssertionError("agent did not finish")


def main():
    with TestClient(app) as c:
        r = c.post("/api/auth/register", json={"name": "مریم", "email": "m@example.com", "password": "secret12"})
        assert r.status_code == 200, r.text
        h = {"Authorization": "Bearer " + r.json()["token"]}
        assert c.post("/api/auth/login", json={"email": "m@example.com", "password": "bad"}).status_code == 400

        bot_id = c.post("/api/bots", json={"message": "یک بات ثبت‌نام کارگاه آبرنگ می‌خواهم"}, headers=h).json()["id"]
        msgs = wait_idle(c, h, bot_id)
        assert msgs[-1]["meta"]["kind"] == "questions", msgs[-1]

        c.post(f"/api/bots/{bot_id}/messages", json={"text": "ظرفیت ۲ نفر"}, headers=h)
        msgs = wait_idle(c, h, bot_id)
        res = msgs[-1]
        assert res["meta"]["kind"] == "result", res
        assert res["meta"]["passed"] == res["meta"]["total"], res
        assert "repair" in calls
        v1 = res["meta"]["version_id"]

        # simulator
        r = c.post(f"/api/bots/{bot_id}/sim", json={"text": "/start", "user": "u1", "version_id": v1}, headers=h).json()
        assert "خوش آمدید" in r["replies"][0]["text"]

        # change request -> v2 with regression tests
        c.post(f"/api/bots/{bot_id}/messages", json={"text": "فهرست انتظار هم اضافه کن"}, headers=h)
        msgs = wait_idle(c, h, bot_id)
        res = msgs[-1]
        assert res["meta"]["kind"] == "result" and res["meta"]["version"] == 2, res
        assert res["meta"]["passed"] == res["meta"]["total"], res
        assert any("waitlist.enabled" in d for d in res["meta"]["diff"]), res["meta"]["diff"]
        v2 = c.get(f"/api/bots/{bot_id}/versions/{res['meta']['version_id']}", headers=h).json()
        names = [t["name"] for t in v2["tests"]]
        assert "ظرفیت دو نفره" in names and "انتظار" in names and "ظرفیت و فهرست انتظار" in names, names

        d = c.get(f"/api/bots/{bot_id}/data?scope=sandbox", headers=h).json()
        assert d["template"] == "workshop"
        bot = c.get(f"/api/bots/{bot_id}", headers=h).json()
        assert [v["number"] for v in bot["versions"]] == [2, 1]
        print("steps:", json.dumps([m["content"] for m in msgs if m["role"] == "step"], ensure_ascii=False))
        print("ALL OK; llm calls:", calls)


if __name__ == "__main__":
    main()
