import grpc
from concurrent import futures
import random
import time
import os
import drone_pb2
import drone_pb2_grpc
import raft_pb2
import raft_pb2_grpc


# Global Raft State
servers    = {}       # dict of node_id -> host:port
id         = 0        # node's ID
myTerm     = 0        # current term number
timer      = 0        # increments every ms, resets on heartbeat
o          = 0        # operation index counter
timerLimit = 1000     # election timeout (randomized 1500-3000ms on startup)
myState    = "Follower"
votedId    = -1       # who this node voted for in current term
myLeaderId = -1       # current known leader
suspended  = False    # whether node is suspended
globalPeriod = 0      # suspension duration in seconds
commitIndex  = 0      # highest log entry known to be committed
lastApplied  = 0      # highest log entry applied to state machine
logs         = []     # the node's operation log
myDict       = {}     # key-value store (the replicated state)
nextIndex    = {}     # leader only: next log index to send to each follower
matchIndex   = {}     # leader only: highest log index known replicated on each follower
inSystem     = False  # whether this node is in the cluster


# Node Management
def add_node(node_id, node_address):
    """Dynamically add a new peer to the cluster."""
    global servers, nextIndex, matchIndex

    if node_id in servers:
        return (False, f"Node {node_id} already exists")

    servers[node_id] = node_address

    if myState == "Leader":
        # Initialize tracking state for the new peer
        nextIndex[node_id]  = commitIndex + 1
        matchIndex[node_id] = 0

        # Notify all existing peers about the new node
        for key in servers:
            if key == id:
                continue
            try:
                channel = grpc.insecure_channel(servers[key])
                stub    = raft_pb2_grpc.RaftServiceStub(channel)
                print(f"Node {id} sends RPC AddNode to Node {key}")
                stub.AddNode(raft_pb2.AddNodeRequest(
                    nodeId=node_id, nodeAddress=node_address))
            except grpc.RpcError:
                continue
    else:
        # Forward to leader
        channel = grpc.insecure_channel(servers[myLeaderId])
        stub    = raft_pb2_grpc.RaftServiceStub(channel)
        print(f"Node {id} sends RPC AddNode to Node {myLeaderId}")
        stub.AddNode(raft_pb2.AddNodeRequest(
            nodeId=node_id, nodeAddress=node_address))

    print(f"Added node {node_id} at {node_address}")
    return (True, f"Node {node_id} added successfully")


def invoke_term_change(term):
    """Revert to follower state when a higher term is discovered."""
    global myLeaderId, votedId, timer, myState, myTerm

    if myState != "Follower" or term != myTerm:
        print(f"I am a follower. Term: {term}")

    timer      = 0
    myTerm     = term
    myLeaderId = -1
    votedId    = -1
    myState    = "Follower"


def init_servers():
    """Load cluster peers from config2.conf."""
    global servers, inSystem
    servers = {}
    with open("config2.conf", "r") as f:
        for line in f:
            parts = line.split(" ")
            servers[int(parts[0])] = f'{parts[1]}:{parts[2].rstrip()}'
            if int(parts[0]) == id:
                inSystem = True


def startup():
    """Initialize all global state and read config."""
    global id, myTerm, timer, timerLimit, myState, votedId, servers, myPort, inSystem
    global myLeaderId, suspended, globalPeriod, commitIndex, lastApplied, o
    global logs, myDict, nextIndex, matchIndex

    id       = int(os.environ.get("NODE_ID", 0))
    inSystem = False

    init_servers()

    myPort       = os.environ.get("NODE_PORT", "50053")
    suspended    = False
    myDict       = {}
    logs         = []
    nextIndex    = {}
    matchIndex   = {}
    lastApplied  = 0
    commitIndex  = 0
    globalPeriod = 0
    myTerm       = 0
    timer        = 0
    timerLimit   = random.randint(1500, 3000)  # randomized election timeout
    myState      = "Follower"
    votedId      = -1
    myLeaderId   = -1
    o            = 0

    print(f"The server starts at {myPort}")
    print("I am a follower. Term: 0")


# Raft
def request_vote(term, candidateId, lastLogIndex, lastLogTerm):
    """
    Handle incoming RequestVote RPC.
    Returns (term, granted) — grants vote if candidate log is at least as up to date.
    """
    global votedId, myTerm, myState, logs

    # If candidate has higher term, update and retry
    if term > myTerm:
        myTerm  = term
        votedId = -1
        return request_vote(term, candidateId, lastLogIndex, lastLogTerm)

    # Reject if stale term or already voted this term
    if term < myTerm or votedId != -1:
        return (myTerm, False)

    # Reject if candidate log is behind ours
    if lastLogIndex < len(logs):
        return (myTerm, False)

    # Reject if last log term doesn't match
    if lastLogIndex != 0 and logs[lastLogIndex - 1]["term"] != lastLogTerm:
        return (myTerm, False)

    votedId = candidateId
    myState = "Follower"

    print(f"Voted for node {candidateId}")
    print(f"I am a follower. Term: {myTerm}")

    return (myTerm, True)


def append_entries(term, leaderId, prevLogIndex, prevLogTerm, entries, leaderCommit):
    """
    Handle incoming AppendEntries RPC.
    Used for both heartbeats (empty entries) and log replication.
    Returns (term, success).
    """
    global myTerm, myState, timer, myLeaderId, logs, commitIndex

    # Reset election timer on every AppendEntries
    timer = 0

    # Reject if leader term is stale
    if myTerm > term:
        return (myTerm, False)

    # Reject if log doesn't contain prevLogIndex entry
    if prevLogIndex > len(logs):
        return (myTerm, False)

    # Find where our log diverges from leader's and truncate
    entriesIndex = 0
    logsIndex    = prevLogIndex

    while logsIndex < len(logs) and entriesIndex < len(entries):
        if logs[logsIndex] != entries[entriesIndex]:
            logs = logs[0:logsIndex]
            break
        logsIndex    += 1
        entriesIndex += 1

    # Append any new entries from leader
    logs += entries[entriesIndex:]

    # Advance commit index if leader has committed further
    if leaderCommit > commitIndex:
        commitIndex = min(leaderCommit, prevLogIndex + len(entries))

    if term > myTerm:
        invoke_term_change(term)
    else:
        myState = "Follower"
        timer   = 0

    myLeaderId = leaderId

    return (myTerm, True)


def get_leader():
    """Return the current known leader ID and address."""
    global myLeaderId, votedId, servers

    print("Command from client: getleader")

    if myLeaderId != -1:
        print(f"{myLeaderId} {servers[myLeaderId]}")
        return (myLeaderId, servers[myLeaderId])

    if votedId != -1:
        print(f"{votedId} {servers[votedId]}")
        return (votedId, servers[votedId])

    print("None")
    return ("None", "None")


def suspend(period):
    """Suspend this node for a given number of seconds (simulates failure)."""
    global suspended, globalPeriod

    print(f"Command from client: suspend {period}")
    print(f"Sleeping for {period} seconds")

    suspended    = True
    globalPeriod = period


def update_log(cmd):
    """
    Append a command to the log.
    If leader: appends directly.
    If follower: forwards to leader via SendDroneCommand RPC.
    """
    global logs, o

    if myState == "Candidate":
        return False, "no leader"

    if myState == "Leader":
        o += 1
        logs.append({"command": f"cmd {cmd}", "term": myTerm, "operationIND": o})
        return True, "None"

    if myLeaderId == -1:
        return False, "no leader elected yet"

    # Forward to leader
    channel = grpc.insecure_channel(servers[myLeaderId])
    stub    = raft_pb2_grpc.RaftServiceStub(channel)

    print(f"Node {id} sends RPC SendDroneCommand to Node {myLeaderId}")

    try:
        response = stub.SendDroneCommand(
            raft_pb2.DroneCommandRequest(command=cmd))
    except grpc.RpcError:
        return False, "could not reach leader"

    return response.success, response.message


def get_val(key):
    """Look up a key in the replicated key-value store."""
    if key not in myDict:
        return (False, "None")
    return (True, myDict[key])


def apply_commits():
    """
    Apply all committed log entries to the state machine.
    Drone commands are forwarded to the update service.
    Key-value commands are stored in myDict.
    """
    global myDict, lastApplied

    while lastApplied < commitIndex:
        entry   = logs[lastApplied]
        command = entry["command"]

        if command.startswith("cmd "):
            # Forward drone command to update service
            actual_cmd = command[4:]
            try:
                print(f"applying command {actual_cmd}")
                channel = grpc.insecure_channel("update:50054")
                stub    = drone_pb2_grpc.UpdateStub(channel)
                stub.SendCommand(drone_pb2.Command(text=actual_cmd))
            except Exception as e:
                print(f"Failed to apply drone command '{actual_cmd}': {e}")
        else:
            # Store key-value pair
            parts = command.split(" ", 1)
            if len(parts) == 2:
                myDict[parts[0]] = parts[1]
            else:
                print(f"inaccurate command")

        lastApplied += 1


# State Handlers
def handle_leader_init():
    """Initialize leader state — called when this node wins an election."""
    global myState, myLeaderId, nextIndex, matchIndex

    myState    = "Leader"
    myLeaderId = id
    nextIndex  = {}
    matchIndex = {}

    print(f"I am a leader. Term: {myTerm}")

    # Initialize tracking indexes for all peers
    for key in servers:
        if key == id:
            continue
        nextIndex[key]  = commitIndex + 1
        matchIndex[key] = 0


def handle_candidate_init():
    """
    Transition to candidate state and start a leader election.
    Sends RequestVote to all peers and becomes leader if majority votes received.
    """
    global timer, myTerm, myState, votedId, myLeaderId

    print("The leader is dead")
    timer = 0
    invoke_term_change(myTerm + 1)
    myState = "Candidate"
    print(f"I am a candidate. Term: {myTerm}")

    vote_count = 1  # vote for self
    votedId    = id
    reachable  = 1
    print(f"Voted for node {id}")

    for key in servers:
        if key == id:
            continue
        try:
            channel     = grpc.insecure_channel(servers[key])
            stub        = raft_pb2_grpc.RaftServiceStub(channel)
            lastLogTerm = logs[-1]["term"] if logs else 0

            print(f"Node {id} sends RPC RequestVote to Node {key}")

            params   = raft_pb2.RequestVoteRequest(
                candidate    = raft_pb2.TermCandIDPair(term=myTerm, candidateID=id),
                lastLogIndex = len(logs),
                lastLogTerm  = lastLogTerm,
            )
            response     = stub.RequestVote(params, timeout=0.10)
            term, result = response.result.term, response.result.verdict
            reachable   += 1
        except grpc.RpcError:
            continue

        if term > myTerm:
            invoke_term_change(term)
            return

        vote_count += result == True

    print("Votes received")

    # Become leader if majority of reachable nodes voted for us
    if vote_count >= reachable / 2:
        handle_leader_init()


def handle_follower():
    """Check if election timeout has expired and start election if so."""
    global myState, timer, timerLimit

    if timer >= timerLimit and inSystem:
        handle_candidate_init()


def handle_candidate():
    """If election timeout expires as candidate, start a new election."""
    global timer, timerLimit

    if timer >= timerLimit:
        timerLimit = random.randint(1500, 3000)
        invoke_term_change(myTerm)


def leader_reset():
    """Force this node back to follower state (used by AddNode flow)."""
    global myState, inSystem
    myState  = "Follower"
    inSystem = True


def handle_leader():
    """
    Send AppendEntries (heartbeat + log replication) to all followers every 1 second.
    Also advances commitIndex when majority of followers have replicated entries.
    """
    global timer, commitIndex, nextIndex, matchIndex, logs

    # Only send heartbeats every 1000ms
    if timer % 1000 != 0:
        return

    timer = 0

    for key in servers:
        if key == id:
            continue

        # Retry loop to handle log inconsistencies
        while True:
            try:
                channel      = grpc.insecure_channel(servers[key])
                stub         = raft_pb2_grpc.RaftServiceStub(channel)
                prevLogIndex = nextIndex[key] - 1
                prevLogTerm  = 0

                if logs and prevLogIndex != 0 and (prevLogIndex - 1) < len(logs):
                    prevLogTerm = logs[prevLogIndex - 1]["term"]

                paramEntries = [form_log_entry_message(x) for x in logs[prevLogIndex:]]
                params       = raft_pb2.AppendEntriesRequest(
                    leader       = raft_pb2.TermLeaderIDPair(term=myTerm, leaderID=id),
                    prevLogIndex = prevLogIndex,
                    prevLogTerm  = prevLogTerm,
                    leaderCommit = commitIndex,
                )
                params.entries.extend(paramEntries)

                print(f"Node {id} sends RPC AppendEntries to Node {key}")

                response     = stub.AppendEntries(params, timeout=0.10)
                term, result = response.result.term, response.result.verdict

            except grpc.RpcError:
                break

            if result:
                # Update tracking indexes on success
                nextIndex[key]  = matchIndex[key] = prevLogIndex + len(paramEntries) + 1
                matchIndex[key] -= 1
                nextIndex[key]   = max(nextIndex[key], 1)
                break

            if term > myTerm:
                invoke_term_change(term)
                return

            # Decrement nextIndex and retry on failure
            nextIndex[key] -= 1
            if nextIndex[key] == 0:
                nextIndex[key] = 1
                break

    # Advance commitIndex if majority have replicated
    while commitIndex < len(logs):
        newCommitIndex    = commitIndex + 1
        reachable_servers = 1 + len(matchIndex)
        validServers      = 1

        for key in matchIndex:
            if matchIndex[key] >= newCommitIndex:
                validServers += 1

        if validServers >= reachable_servers / 2:
            commitIndex = newCommitIndex
        else:
            break


def extract_log_entry_message(entry):
    """Convert a protobuf LogEntry to a Python dict."""
    return {
        "command"      : entry.command,
        "term"         : entry.term,
        "operationIND" : entry.operationIND
    }


def form_log_entry_message(entry):
    """Convert a Python dict log entry to a protobuf LogEntry."""
    return raft_pb2.LogEntry(
        command      = entry["command"],
        term         = entry["term"],
        operationIND = entry["operationIND"]
    )


def handle_current_state():
    """Main state machine tick — called every millisecond."""
    apply_commits()
    if myState == "Follower":
        handle_follower()
    if myState == "Candidate":
        handle_candidate()
    elif myState == "Leader":
        handle_leader()


# gRPC Service
class ServerService(drone_pb2_grpc.ServerServicer):
    def __init__(self):
        # Connect to drone update service for command forwarding
        self.channel = grpc.insecure_channel("update:50054")
        self.stub    = drone_pb2_grpc.UpdateStub(self.channel)

    def SendCommand(self, request, context):
        """Handle drone commands from client."""
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

        try:
            response = self.stub.SendCommand(drone_pb2.Command(text=cmd))
            return response
        except Exception as e:
            return drone_pb2.Reply(
                text=f"Error communicating with update service: {str(e)}"
            )

    def RequestVote(self, request, context):
        """Handle incoming vote request from a candidate."""
        print(f"Node {id} runs RPC RequestVote called by Node {request.candidate.candidateID}")

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
        """Handle incoming heartbeat or log replication from leader."""
        print(f"Node {id} runs RPC AppendEntries called by Node {request.leader.leaderID}")

        entries  = [extract_log_entry_message(e) for e in request.entries]
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
        """Return current leader info to client."""
        leader = get_leader()
        if leader[0] == "None":
            return raft_pb2.GetLeaderResponse(nodeId=-1)
        return raft_pb2.GetLeaderResponse(nodeId=leader[0], nodeAddress=leader[1])

    def Suspend(self, request, context):
        """Suspend this node for a given period (simulates failure)."""
        suspend(request.period)
        return raft_pb2.Empty()

    def AddNode(self, request, context):
        """Handle request to add a new node to the cluster."""
        print(f"Node {id} runs RPC AddNode called by Node {request.nodeId}")
        success, message = add_node(request.nodeId, request.nodeAddress)
        return raft_pb2.AddNodeResponse(success=success, message=message)

    def SendDroneCommand(self, request, context):
        """Handle forwarded drone command from a follower."""
        print(f"Node {id} runs RPC SendDroneCommand called by Node {myLeaderId}")
        success, error = update_log(request.command)
        return raft_pb2.DroneCommandResponse(
            success = success,
            message = error if error else "OK"
        )

    def ViewLog(self, request, context):
        """Return the full log for inspection."""
        response_logs = []
        for entry in logs:
            response_logs.append(raft_pb2.LogEntries(
                op_command   = entry["command"],
                op_term      = entry["term"],
                operationIND = entry["operationIND"],
            ))
        return raft_pb2.LogResponse(logs=response_logs)

    def ResetLeader(self, request, context):
        """Force this node back to follower (used when adding new nodes)."""
        leader_reset()
        return raft_pb2.LogRequest(ar=1)

    def SetVal(self, request, context):
        """Placeholder — key-value sets handled via update_log."""
        print("hi")

    def GetVal(self, request, context):
        """Placeholder — key-value gets handled via get_val."""
        print("hi")


# Server Startup
def make_server():
    """Create and configure a new gRPC server instance."""
    s = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    drone_pb2_grpc.add_ServerServicer_to_server(ServerService(), s)
    raft_pb2_grpc.add_RaftServiceServicer_to_server(ServerService(), s)
    s.add_insecure_port(myPort)
    return s


def serve():
    """Main server loop — handles suspension and state machine ticks."""
    global timer, suspended

    server = make_server()
    server.start()
    print(f"Server running on {myPort}")

    while True:
        if suspended:
            server.stop(0)
            time.sleep(globalPeriod)
            server = make_server()
            server.start()
            suspended = False

        handle_current_state()
        time.sleep(0.001)
        timer += 1


if __name__ == "__main__":
    startup()
    serve()