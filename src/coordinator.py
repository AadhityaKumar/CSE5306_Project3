import grpc
import uuid
import os
from concurrent import futures
import tpc_pb2
import tpc_pb2_grpc
import time

NODE_ID = os.environ.get("NODE_ID", "coordinator")
PORT    = int(os.environ.get("PORT", "50062"))

PARTICIPANTS = [
    ("aggregation", os.environ.get("AGGREGATION_HOST", "tpc-aggregation")),
    ("analysis",    os.environ.get("ANALYSIS_HOST",    "tpc-analysis")),
    ("update",      os.environ.get("UPDATE_HOST",      "tpc-update")),
    ("airdata",     os.environ.get("AIRDATA_HOST",     "tpc-airdata")),
    ("imu",         os.environ.get("IMU_HOST",         "tpc-imu")),
]

PARTICIPANT_PORT = int(os.environ.get("PARTICIPANT_PORT", "50060"))

def get_stub(host):
    return tpc_pb2_grpc.ParticipantStub(grpc.insecure_channel(f"{host}:{PARTICIPANT_PORT}"))

def run_voting_phase(transaction_id, operation):
    print(f"\n[{NODE_ID}] ── VOTING PHASE {transaction_id} ──")
    votes = {}
    for (node_id, host) in PARTICIPANTS:
        print(f"Phase voting of Node {NODE_ID} sends RPC RequestVote to Phase voting of Node {node_id}")
        
        # Retry up to 5 times in case participant isn't ready yet
        success = False
        for attempt in range(5):
            try:
                response       = get_stub(host).RequestVote(tpc_pb2.VoteRequest(
                    transaction_id = transaction_id,
                    coordinator_id = NODE_ID,
                    operation      = operation,
                ))
                votes[node_id] = response.vote_commit
                print(f"[{NODE_ID}] Received {'COMMIT' if response.vote_commit else 'ABORT'} from {node_id}")
                success = True
                break
            except Exception as e:
                print(f"[{NODE_ID}] Attempt {attempt+1} — no response from {node_id}: {e}")
                time.sleep(2)

        if not success:
            print(f"[{NODE_ID}] {node_id} unreachable after 5 attempts — treating as ABORT")
            votes[node_id] = False
        
    return votes

def run_decision_phase(transaction_id, votes):
    print(f"\n[{NODE_ID}] ── DECISION PHASE {transaction_id} ──")
    
    # Intra-node: voting → decision phase
    print(f"Phase voting of Node {NODE_ID} sends RPC NotifyDecisionPhase to Phase decision of Node {NODE_ID}")
    print(f"Phase decision of Node {NODE_ID} runs RPC NotifyDecisionPhase called by Phase voting of Node {NODE_ID}")

    global_commit = all(votes.values())
    print(f"[{NODE_ID}] Decision: {'GLOBAL COMMIT' if global_commit else 'GLOBAL ABORT'}")

    for (node_id, host) in PARTICIPANTS:
        print(f"Phase decision of Node {NODE_ID} sends RPC Deliver to Phase decision of Node {node_id}")
        try:
            get_stub(host).Deliver(tpc_pb2.Decision(
                transaction_id = transaction_id,
                commit         = global_commit,
            ))
        except Exception as e:
            print(f"[{NODE_ID}] No ACK from {node_id}: {e}")

    return global_commit

class CoordinatorService(tpc_pb2_grpc.CoordinatorServicer):

    def StartTransaction(self, request, context):
        transaction_id = request.transaction_id or str(uuid.uuid4())
        print(f"\n{'═'*50}\n[{NODE_ID}] NEW TRANSACTION: {transaction_id}\n{'═'*50}")

        votes         = run_voting_phase(transaction_id, request.operation)
        global_commit = run_decision_phase(transaction_id, votes)

        print(f"\n[{NODE_ID}] DONE — {'COMMITTED' if global_commit else 'ABORTED'}\n")
        return tpc_pb2.Acknowledgement(
            transaction_id = transaction_id,
            node_id        = NODE_ID,
            success        = global_commit,
        )

    def NotifyVotingPhase(self, request, context):
        return tpc_pb2.PhaseAck(transaction_id=request.transaction_id, received=True)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    tpc_pb2_grpc.add_CoordinatorServicer_to_server(CoordinatorService(), server)
    server.add_insecure_port(f"[::]:{PORT}")
    server.start()
    print(f"[{NODE_ID}] Coordinator listening on port {PORT}")
    server.wait_for_termination()

if __name__ == "__main__":
    serve()