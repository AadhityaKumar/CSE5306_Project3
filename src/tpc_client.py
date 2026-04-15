import grpc
import os
import uuid
import time
import tpc_pb2
import tpc_pb2_grpc

COORDINATOR_HOST = os.environ.get("COORDINATOR_HOST", "tpc-coordinator")
COORDINATOR_PORT = int(os.environ.get("COORDINATOR_PORT", "50062"))

# adding to wait for coordinator
def wait_for_coordinator(stub, retries=10, delay=3):
    for attempt in range(retries):
        try:
            # dummy transaction to test connectivity
            stub.StartTransaction(tpc_pb2.VoteRequest(
                transaction_id = "ping",
                coordinator_id = "tpc-client",
                operation      = "ping",
            ))
            return True
        except grpc.RpcError:
            print(f"[tpc-client] Coordinator not ready, retrying ({attempt+1}/{retries})...")
            time.sleep(delay)
    return False

def run():
    # Give coordinator time to start
    time.sleep(8)

    print(f"[tpc-client] Connecting to {COORDINATOR_HOST}:{COORDINATOR_PORT}")
    channel = grpc.insecure_channel(f"{COORDINATOR_HOST}:{COORDINATOR_PORT}")
    stub    = tpc_pb2_grpc.CoordinatorStub(channel)

    transaction_id = str(uuid.uuid4())
    print(f"\n[tpc-client] Triggering transaction {transaction_id}")

    #added to get error output to the client
    try:
        response = stub.StartTransaction(
            tpc_pb2.VoteRequest(
                transaction_id = transaction_id,
                coordinator_id = "tpc-client",
                operation      = "commit_telemetry_batch",
            ),
            timeout=30
        )
        print(f"\n[tpc-client] Result — success: {response.success}")
    except grpc.RpcError as e:
        print(f"\n[tpc-client] gRPC ERROR: {e.code()}")
        print(f"[tpc-client] Details: {e.details()}")

if __name__ == "__main__":
    run()