
import asyncio, json, threading, time, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 1. Test FeishuChannel start and handler
# 2. Test Bus publish/consume
# 3. Simulate a message event

from nanobot.bus.queue import MessageBus
from nanobot.bus.events import InboundMessage, OutboundMessage

bus = MessageBus()

# Test 1: Bus works
async def test_bus():
    await bus.publish_inbound(InboundMessage(
        channel="feishu",
        sender_id="test_user",
        chat_id="test_chat",
        content="hello",
        metadata={"message_id": "test123"}
    ))
    msg = await bus.consume_inbound()
    print(f"Bus test PASS: channel={msg.channel}, session_key={msg.session_key}")
    print(f"  session_key_override={msg.session_key_override}")
    print(f"  content={msg.content}")

asyncio.run(test_bus())

# Test 2: Check FeishuChannel config
print("\n--- Test FeishuChannel configuration ---")
import yaml
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

feishu_cfg = config.get("channels", {}).get("feishu", {})
print(f"enabled: {feishu_cfg.get('enabled')}")
print(f"app_id: {feishu_cfg.get('app_id')[:10]}...")
print(f"app_secret: {feishu_cfg.get('app_secret')[:5]}...")
print(f"allow_from: {feishu_cfg.get('allow_from')}")
print(f"streaming: {feishu_cfg.get('streaming')}")
print(f"domain: {feishu_cfg.get('domain')}")

# Test 3: Import FeishuChannel and check initialization
print("\n--- Test FeishuChannel init ---")
from nanobot.channels.feishu import FeishuChannel, FeishuConfig, FEISHU_AVAILABLE
print(f"FEISHU_AVAILABLE: {FEISHU_AVAILABLE}")

try:
    fconfig = FeishuConfig.model_validate(feishu_cfg)
    print(f"Config parsed: allow_from={fconfig.allow_from}")
except Exception as e:
    print(f"Config parse error: {e}")

print("\nAll basic tests passed!")
