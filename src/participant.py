import grpc
import random
import os
from concurrent import futures
import tpc_pb2
import tpc_pb2_grpc

NODE_ID = os.environ.get("NODE_ID", "participant")
PORT    = int(os.environ.get("PORT", "50060"))

class ParticipantService(tpc_pb2_grpc.ParticipantServicer):
    def RequestVote(self, request, context):
        # Q1 — server side print
        print(f"Phase voting of Node {NODE_ID} runs RPC RequestVote called by Phase voting of Node {request.coordinator_id}")
        
        vote_commit = random.random() > 0.2
        reason      = "" if vote_commit else "Resource unavailable"
        
        print(f"[{NODE_ID}] Voting {'COMMIT' if vote_commit else 'ABORT'} for transaction {request.transaction_id}")
        
        # Intra-node: simulate voting → decision phase notification
        print(f"Phase voting of Node {NODE_ID} sends RPC NotifyDecisionPhase to Phase decision of Node {NODE_ID}")
        print(f"Phase decision of Node {NODE_ID} runs RPC NotifyDecisionPhase called by Phase voting of Node {NODE_ID}")

        return tpc_pb2.VoteResponse(
            transaction_id = request.transaction_id,
            node_id        = NODE_ID,
            vote_commit    = vote_commit,
            reason         = reason,
        )

    def Deliver(self, request, context):
        # Q2 — server side print
        print(f"Phase decision of Node {NODE_ID} runs RPC Deliver called by Phase decision of Node coordinator")
        
        outcome = "COMMITTED" if request.commit else "ABORTED"
        print(f"[{NODE_ID}] Transaction {request.transaction_id} → locally {outcome}")

        return tpc_pb2.Acknowledgement(
            transaction_id = request.transaction_id,
            node_id        = NODE_ID,
            success        = True,
        )

    def NotifyDecisionPhase(self, request, context):
        return tpc_pb2.PhaseAck(transaction_id=request.transaction_id, received=True)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    tpc_pb2_grpc.add_ParticipantServicer_to_server(ParticipantService(), server)
    server.add_insecure_port(f"[::]:{PORT}")
    server.start()
    print(f"[{NODE_ID}] Participant listening on port {PORT}")
    server.wait_for_termination()

if __name__ == "__main__":
    serve()