import grpc
from concurrent import futures
import random
import time
import sys
import threading
import drone_pb2
import drone_pb2_grpc
import raft_pb2
import raft_pb2_grpc
import os

# ---------------------------------------------------------------------------
# Global RAFT state
# ---------------------------------------------------------------------------
state_lock = threading.Lock()

servers = {}
id = 0
myTerm = 0
timer = 0
timerLimit = 0
myState = "Follower"
votedId = -1
myLeaderId = -1
suspended = False
globalPeriod = 0
commitIndex = 0
lastApplied = 0
logs = []
myDict = {}
nextIndex = {}
matchIndex = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def add_node(node_id, node_address):
    global servers, nextIndex, matchIndex

    with state_lock:
        if node_id in servers:
            return (False, f"Node {node_id} already exists")

        servers[node_id] = node_address

        with open("config.conf", "a") as f:
            f.write(f"{node_id} {node_address.replace(':', ' ')}\n")

        if myState == "Leader":
            nextIndex[node_id] = commitIndex + 1
            matchIndex[node_id] = 0

    print(f"Added node {node_id} at {node_address}")
    return (True, f"Node {node_id} added successfully")


def invoke_term_change(term):
    global myLeaderId, votedId, timer, myState, myTerm

    if myState != "Follower" or term != myTerm:
        print(f"I am a follower. Term: {term}")

    timer = 0
    myTerm = term
    myLeaderId = -1
    votedId = -1
    myState = "Follower"


def init_servers():
    global servers
    servers = {}
    with open("config.conf", "r") as f:
        for line in f:
            parts = line.split(" ")
            servers[int(parts[0])] = f'{parts[1]}:{parts[2].rstrip()}'


def startup():
    global id, myTerm, timer, timerLimit, myState, votedId, servers
    global myLeaderId, suspended, globalPeriod, commitIndex, lastApplied
    global logs, myDict, nextIndex, matchIndex

    init_servers()

    id = int(os.environ.get("NODE_ID", 0))
    port = int(os.environ.get("NODE_PORT", 50053))
    suspended = False
    myDict = {}
    logs = []
    nextIndex = {}
    matchIndex = {}
    lastApplied = 0
    commitIndex = 0
    globalPeriod = 0
    myTerm = 0
    timer = 0
    timerLimit = random.randint(150, 300)
    myState = "Follower"
    votedId = -1
    myLeaderId = -1

    print(f"The server starts at {servers[id]}")
    print("I am a follower. Term: 0")

# ---------------------------------------------------------------------------
# RAFT logic
# ---------------------------------------------------------------------------

def request_vote(term, candidateId, lastLogIndex, lastLogTerm):
    global votedId, myTerm, myState, logs

    with state_lock:
        if term > myTerm:
            myTerm = term
            votedId = -1

        if term < myTerm or votedId != -1:
            return (myTerm, False)

        if lastLogIndex < len(logs):
            return (myTerm, False)

        if lastLogIndex != 0 and logs[lastLogIndex - 1]["term"] != lastLogTerm:
            return (myTerm, False)

        votedId = candidateId
        myState = "Follower"

        print(f"Voted for node {candidateId}")
        print(f"I am a follower. Term: {myTerm}")

        return (myTerm, True)


def append_entries(term, leaderId, prevLogIndex, prevLogTerm, entries, leaderCommit):
    global myTerm, myState, timer, myLeaderId, logs, commitIndex

    with state_lock:
        timer = 0

        if myTerm > term:
            return (myTerm, False)

        if prevLogIndex > len(logs):
            return (myTerm, False)

        entriesIndex = 0
        logsIndex = prevLogIndex

        while logsIndex < len(logs) and entriesIndex < len(entries):
            if logs[logsIndex] != entries[entriesIndex]:
                logs = logs[0:logsIndex]
                break
            logsIndex += 1
            entriesIndex += 1

        logs += entries[entriesIndex:]

        if leaderCommit > commitIndex:
            commitIndex = min(leaderCommit, prevLogIndex + len(entries))

        if term > myTerm:
            invoke_term_change(term)
        myLeaderId = leaderId

        return (myTerm, True)


def get_leader():
    with state_lock:
        if myLeaderId != -1:
            print(f"{myLeaderId} {servers[myLeaderId]}")
            return (myLeaderId, servers[myLeaderId])

        if votedId != -1:
            print(f"{votedId} {servers[votedId]}")
            return (votedId, servers[votedId])

    print("None")
    return ("None", "None")


def suspend(period):
    global suspended, globalPeriod

    print(f"Command from client: suspend {period}")
    print(f"Sleeping for {period} seconds")

    suspended = True
    globalPeriod = period


def update_log(cmd):
    global logs

    with state_lock:
        state = myState
        leader_id = myLeaderId
        current_term = myTerm

    if state == "Candidate":
        return False, "no leader"

    if state == "Leader":
        with state_lock:
            logs.append({"term": current_term, "command": cmd})
            targIND = len(logs)

        timeout = time.time() + 5.0
        while True:
            with state_lock:
                ci = commitIndex
            if ci >= targIND:
                break
            if time.time() > timeout:
                return (False, "Timed out waiting for commit")
            time.sleep(0.01)

        return True, "None"

    if leader_id == -1:
        return False, "no leader elected yet"

    with state_lock:
        leader_addr = servers[leader_id]

    channel = grpc.insecure_channel(leader_addr)
    stub = raft_pb2_grpc.RaftServiceStub(channel)

    try:
        response = stub.SendDroneCommand(raft_pb2.DroneCommandRequest(command=cmd))
    except grpc.RpcError:
        return False, "could not reach leader"

    return response.success, response.message


def get_val(key):
    with state_lock:
        if key not in myDict:
            return (False, "None")
        return (True, myDict[key])


def apply_commits():
    global myDict, lastApplied

    # Read boundaries under lock, but do network I/O outside
    while True:
        with state_lock:
            if lastApplied >= commitIndex:
                break
            entry = logs[lastApplied]
            lastApplied += 1

        command = entry["command"]

        if command.startswith("cmd "):
            actual_cmd = command[4:]
            try:
                channel = grpc.insecure_channel("update:50054")
                stub = drone_pb2_grpc.UpdateStub(channel)
                stub.SendCommand(drone_pb2.Command(text=actual_cmd))
            except Exception as e:
                print(f"Failed to apply drone command '{actual_cmd}': {e}")
        else:
            parts = command.split(" ")
            with state_lock:
                myDict[parts[0]] = parts[1]


def handle_leader_init():
    global myState, myLeaderId, nextIndex, matchIndex

    # Must be called with state_lock already held
    myState = "Leader"
    print(f"I am a leader. Term: {myTerm}")
    myLeaderId = id
    nextIndex = {}
    matchIndex = {}

    for key in servers:
        if key == id:
            continue
        nextIndex[key] = commitIndex + 1
        matchIndex[key] = 0


def handle_candidate_init():
    global timer, myTerm, myState, votedId, myLeaderId

    print("The leader is dead")

    with state_lock:
        timer = 0
        invoke_term_change(myTerm + 1)
        myState = "Candidate"
        current_term = myTerm
        print(f"I am a candidate. Term: {myTerm}")
        vote_count = 1
        votedId = id
        print(f"Voted for node {id}")
        peers = dict(servers)

    reachable = 1  # count ourselves as reachable

    for key in peers:
        if key == id:
            continue
        try:
            channel = grpc.insecure_channel(peers[key])
            stub = raft_pb2_grpc.RaftServiceStub(channel)

            with state_lock:
                lastLogTerm = logs[-1]["term"] if logs else 0
                lastLogIndex = len(logs)

            params = raft_pb2.RequestVoteRequest(
                candidate=raft_pb2.TermCandIDPair(term=current_term, candidateID=id),
                lastLogIndex=lastLogIndex,
                lastLogTerm=lastLogTerm,
            )
            response = stub.RequestVote(params)
            term, result = response.result.term, response.result.verdict
            reachable += 1  # only count nodes that actually responded

        except grpc.RpcError:
            continue  # node is down, don't count it toward majority

        with state_lock:
            if term > myTerm:
                invoke_term_change(term)
                return
            if result:
                vote_count += 1

    print("Votes received")
    with state_lock:
        if myState == "Candidate" and myTerm == current_term:
            # Majority of reachable nodes, not total configured nodes
            if vote_count >= reachable / 2:
                handle_leader_init()

def handle_follower():
    global myState, timer, timerLimit

    # Called with state_lock held by handle_current_state
    if timer >= timerLimit:
        # Release lock before candidate init (which re-acquires it)
        pass  # flag handled below


def handle_candidate():
    global timer, timerLimit

    # Called with state_lock held by handle_current_state
    if timer >= timerLimit:
        timerLimit = random.randint(150, 300)
        invoke_term_change(myTerm)


def extract_log_entry_message(entry):
    return {"term": entry.term, "command": entry.command}


def form_log_entry_message(entry):
    return raft_pb2.LogEntry(term=entry["term"], command=entry["command"])


def handle_leader():
    global timer, commitIndex, nextIndex, matchIndex, logs

    # Called with state_lock held by handle_current_state
    if timer % 50 != 0:
        return

    timer = 0
    peers = dict(servers)
    current_term = myTerm
    current_id = id
    snapshot_nextIndex = dict(nextIndex)
    snapshot_logs = list(logs)
    snapshot_commitIndex = commitIndex


    for key in peers:
        if key == current_id:
            continue

        ni = snapshot_nextIndex.get(key, 1)

        while True:
            try:
                channel = grpc.insecure_channel(peers[key])
                stub = raft_pb2_grpc.RaftServiceStub(channel)
                prevLogIndex = ni - 1
                prevLogTerm = 0
                if snapshot_logs and prevLogIndex != 0:
                    prevLogTerm = snapshot_logs[prevLogIndex - 1]["term"]

                paramEntries = [form_log_entry_message(x) for x in snapshot_logs[prevLogIndex:]]
                params = raft_pb2.AppendEntriesRequest(
                    leader=raft_pb2.TermLeaderIDPair(term=current_term, leaderID=current_id),
                    prevLogIndex=prevLogIndex,
                    prevLogTerm=prevLogTerm,
                    leaderCommit=snapshot_commitIndex,
                )
                params.entries.extend(paramEntries)
                response = stub.AppendEntries(params)
                term, result = response.result.term, response.result.verdict
            except grpc.RpcError:
                break

            if result:
                with state_lock:
                    nextIndex[key] = matchIndex[key] = prevLogIndex + len(paramEntries) + 1
                    matchIndex[key] -= 1
                    nextIndex[key] = max(nextIndex[key], 1)
                break

            with state_lock:
                if term > myTerm:
                    invoke_term_change(term)
                    return
                nextIndex[key] = max(nextIndex.get(key, 1) - 1, 1)
                ni = nextIndex[key]
                if ni == 1 and prevLogIndex == 0:
                    break

    with state_lock:
        while commitIndex < len(logs):
            newCommitIndex = commitIndex + 1
            validServers = 1
            for key in matchIndex:
                if matchIndex[key] >= newCommitIndex:
                    validServers += 1
            if validServers >= len(servers) / 2 + 1:
                commitIndex = newCommitIndex
            else:
                break


def handle_current_state():
    apply_commits()

    # Check state and timer under lock, but do network I/O (candidate init) outside
    with state_lock:
        state = myState
        t = timer
        tl = timerLimit

    if state == "Follower" and t >= tl:
        handle_candidate_init()  # acquires lock internally
        return

    with state_lock:
        if myState == "Candidate":
            handle_candidate()  # fast, no I/O
        elif myState == "Leader":
            handle_leader()     # does I/O but snapshots state first


# ---------------------------------------------------------------------------
# gRPC service
# ---------------------------------------------------------------------------

class ServerService(drone_pb2_grpc.ServerServicer):
    def __init__(self):
        self.channel = grpc.insecure_channel("update:50054")
        self.stub = drone_pb2_grpc.UpdateStub(self.channel)

    def SendCommand(self, request, context):
        cmd = request.text.strip().lower()

        if cmd == "help":
            return drone_pb2.Reply(text=(
                "Available commands:\n"
                "  help\n"
                "  status\n"
                "  health\n"
                "  list\n"
                "  sensor <name>\n"
                "  alerts\n"
                "  quit"
            ))

        if cmd == "quit":
            return drone_pb2.Reply(text="Exiting client.")

        success, error = update_log(cmd)
        if not success:
            return drone_pb2.Reply(text=f"Error: {error}")

        return drone_pb2.Reply(text="Command acknowledged.")

    def RequestVote(self, request, context):
        voted = request_vote(
            request.candidate.term,
            request.candidate.candidateID,
            request.lastLogIndex,
            request.lastLogTerm,
        )
        return raft_pb2.RequestVoteResponse(
            result=raft_pb2.TermResultPair(term=voted[0], verdict=voted[1])
        )

    def AppendEntries(self, request, context):
        entries = [extract_log_entry_message(e) for e in request.entries]
        appended = append_entries(
            request.leader.term,
            request.leader.leaderID,
            request.prevLogIndex,
            request.prevLogTerm,
            entries,
            request.leaderCommit,
        )
        return raft_pb2.AppendEntriesResponse(
            result=raft_pb2.TermResultPair(term=appended[0], verdict=appended[1])
        )

    def GetLeader(self, request, context):
        leader = get_leader()
        if leader[0] == "None":
            return raft_pb2.GetLeaderResponse(nodeId=-1)
        return raft_pb2.GetLeaderResponse(nodeId=leader[0], nodeAddress=leader[1])

    def Suspend(self, request, context):
        suspend(request.period)
        return raft_pb2.Empty()

    def AddNode(self, request, context):
        success, message = add_node(request.nodeId, request.nodeAddress)
        return raft_pb2.AddNodeResponse(success=success, message=message)

    def SendDroneCommand(self, request, context):
        success, error = update_log(request.command)
        return raft_pb2.DroneCommandResponse(
            success=success,
            message=error if error else "OK"
        )


# ---------------------------------------------------------------------------
# Server loop
# ---------------------------------------------------------------------------

def serve():
    global timer, suspended

    port = int(os.environ.get("NODE_PORT", 50053))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    drone_pb2_grpc.add_ServerServicer_to_server(ServerService(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"Server running on {port}")

    while True:
        if suspended:
            server.stop(0)
            time.sleep(globalPeriod)
            server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
            drone_pb2_grpc.add_ServerServicer_to_server(ServerService(), server)
            server.add_insecure_port(f"[::]:{port}")
            server.start()
            suspended = False

        handle_current_state()
        time.sleep(0.001)

        with state_lock:
            timer += 1


if __name__ == "__main__":
    startup()
    serve()