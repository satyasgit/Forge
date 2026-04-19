"""
Verification script for Phase 2: Communication Bus.
Tests Redis connection, JobStore, and MessageBus.
"""
import asyncio
import logging
import uuid
from communication.bus import MessageBus, JobStore, AgentMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_bus():
    print("--- Verifying Phase 2: Communication Bus ---")
    
    # 1. Test JobStore
    store = JobStore()
    job_id = str(uuid.uuid4())
    test_data = {"status": "testing", "meta": "verify_bus"}
    
    print(f"1. Testing JobStore with job_id: {job_id}")
    await store.set_job(job_id, test_data)
    retrieved = await store.get_job(job_id)
    
    if retrieved == test_data:
        print("   ✅ JobStore: Set/Get successful")
    else:
        print(f"   ❌ JobStore: Failed. Expected {test_data}, got {retrieved}")
    
    # 2. Test MessageBus (Pub/Sub)
    bus = MessageBus()
    received_msgs = []
    
    async def on_msg(msg):
        received_msgs.append(msg)
        print(f"   📥 Bus: Received message from {msg.sender}: {msg.content}")

    print("2. Testing MessageBus (Pub/Sub)")
    # Subscribe in background
    sub_task = asyncio.create_task(bus.subscribe(["test_channel"], on_msg))
    await asyncio.sleep(1) # Wait for subscription to stabilize
    
    msg = AgentMessage(
        sender="verifier",
        content="Hello agents!",
        channel="test_channel",
        message_type="broadcast"
    )
    
    await bus.publish(msg)
    await asyncio.sleep(1) # Wait for message to arrive
    
    if len(received_msgs) > 0 and received_msgs[0].content == "Hello agents!":
        print("   ✅ MessageBus: Publish/Subscribe successful")
    else:
        print("   ❌ MessageBus: Failed to receive message")
    
    sub_task.cancel()
    print("--- Verification Complete ---")

if __name__ == "__main__":
    try:
        asyncio.run(verify_bus())
    except Exception as e:
        print(f"❌ Verification failed with error: {e}")
