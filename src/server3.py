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

servers = {}
id = 0
myTerm = 0
timer = 0
o = 0
timerLimit = 1000
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
inSystem = False


def add_node(node_id, node_address):
    """Register a new peer and persist it to config.conf."""
    global servers, nextIndex, matchIndex

    if node_id in servers:
        return (False, f"Node {node_id} already exists")

    # Add to in-memory peer table
    servers[node_id] = node_address

    # Persist to config.conf so the node survives restarts
    #with open("config.conf", "a") as f:
      #  f.write(f"{node_id} {node_address.replace(':', ' ')}\n")

    # If we're the leader, initialize tracking state for the new peer
    if myState == "Leader":
        nextIndex[node_id] = commitIndex + 1
        matchIndex[node_id] = 0
        for key in servers:
            if key == id:
                continue
            try:
                channel = grpc.insecure_channel(servers[key])
                stub = raft_pb2_grpc.RaftServiceStub(channel)
                resp2 = stub.AddNode(raft_pb2.AddNodeRequest(nodeId=node_id, nodeAddress=node_address))
            except  grpc.RpcError:
                continue
    else:
        channel = grpc.insecure_channel(servers[myLeaderId])
        stub = raft_pb2_grpc.RaftServiceStub(channel)
        resp = stub.AddNode(raft_pb2.AddNodeRequest(nodeId=node_id, nodeAddress=node_address))


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
    global servers, inSystem
    servers = {}
    with open("config2.conf", "r") as f:
        for line in f:
            parts = line.split(" ")
            servers[int(parts[0])] = f'{parts[1]}:{parts[2].rstrip()}'
            if int(parts[0]) == id:
                inSystem = True



def startup():
    global id, myTerm, timer, timerLimit, myState, votedId, servers, myPort, inSystem
    global myLeaderId, suspended, globalPeriod, commitIndex, lastApplied, o
    global logs, myDict, nextIndex, matchIndex

    id = int(os.environ.get("NODE_ID", 0))
    inSystem = False

    init_servers()

    myPort = (os.environ.get("NODE_PORT", 50053))
    #id = int(sys.argv[1])
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
    timerLimit = random.randint(1500, 3000)
    myState = "Follower"
    votedId = -1
    myLeaderId = -1
    o = 0

    print(f"The server starts at {myPort}")
    print("I am a follower. Term: 0")


def request_vote(term, candidateId, lastLogIndex, lastLogTerm):
    global votedId, myTerm, myState, logs

    if term > myTerm:
        myTerm = term
        votedId = -1
        return request_vote(term, candidateId, lastLogIndex, lastLogTerm)

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
    print("appending entries")
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
    else:
        myState = "Follower"
        timer = 0
    myLeaderId = leaderId

    return (myTerm, True)


def get_leader():
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
    global suspended, globalPeriod

    print(f"Command from client: suspend {period}")
    print(f"Sleeping for {period} seconds")

    suspended = True
    globalPeriod = period


def update_log(cmd):
    global logs, o

    if myState == "Candidate":
        return False, "no leader"

    if myState == "Leader":
        o += 1
        logs.append({ "command": f"cmd {cmd}", "term": myTerm, "operationIND" : o})
        #targIND = len(logs)

        """
        timeout = time.time() + 5.0
        while commitIndex < targIND:
            if time.time() > timeout:
                return (False, "Timed out waiting for commit")
            time.sleep(0.01)
        """
        return True, "None"

    if myLeaderId == -1:
        return False, "no leader elected yet"
    channel = grpc.insecure_channel(servers[myLeaderId])
    stub = raft_pb2_grpc.RaftServiceStub(channel)

    try:
        response = stub.SendDroneCommand(raft_pb2.DroneCommandRequest(command=cmd))
    except grpc.RpcError:
        return False, "could not reach leader"

    return response.success, response.message


def get_val(key):
    if key not in myDict:
        return (False, "None")
    return (True, myDict[key])


def apply_commits():
    global myDict, lastApplied

    while lastApplied < commitIndex:
        entry = logs[lastApplied]
        command = entry["command"]

        if command.startswith("cmd "):
            actual_cmd = command[4:]
            try:
                print(f"applying command {actual_cmd}")
                channel = grpc.insecure_channel("update:50054")
                stub = drone_pb2_grpc.UpdateStub(channel)
                stub.SendCommand(drone_pb2.Command(text=actual_cmd))
            except Exception as e:
                print(f"Failed to apply drone command '{actual_cmd}': {e}")
        else:
            parts = command.split(" ", 1)
            if len(parts) == 2:
                myDict[parts[0]] = parts[1]
            else:
                print(f"inaccurate command")

        lastApplied += 1


def handle_leader_init():
    global myState, myLeaderId, nextIndex, matchIndex

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
    timer = 0
    invoke_term_change(myTerm + 1)
    myState = "Candidate"
    print(f"I am a candidate. Term: {myTerm}")

    vote_count = 1
    votedId = id
    print(f"Voted for node {id}")
    reachable = 1

    for key in servers:
        if key == id:
            continue
        try:
            channel = grpc.insecure_channel(servers[key])
            stub = raft_pb2_grpc.RaftServiceStub(channel)
            lastLogTerm = logs[-1]["term"] if logs else 0
            params = raft_pb2.RequestVoteRequest(
                candidate=raft_pb2.TermCandIDPair(term=myTerm, candidateID=id),
                lastLogIndex=len(logs),
                lastLogTerm=lastLogTerm,
            )
            response = stub.RequestVote(params, timeout=0.10)
            term, result = response.result.term, response.result.verdict
            reachable += 1
        except grpc.RpcError:
            continue

        if term > myTerm:
            invoke_term_change(term)
            return

        vote_count += result == True

    print("Votes received")
    if vote_count >= reachable / 2:
        handle_leader_init()


def handle_follower():
    global myState, timer, timerLimit

    if timer >= timerLimit and inSystem:
        handle_candidate_init()

def leader_reset():
    global myState, inSystem
    myState = "Follower"
    inSystem = True


def handle_candidate():
    global timer, timerLimit

    if timer >= timerLimit:
        timerLimit = random.randint(1500, 3000)
        invoke_term_change(myTerm)


def extract_log_entry_message(entry):
    #return {"term": entry.term, "command": entry.command}
    return { "command": entry.command, "term": entry.term, "operationIND" : entry.operationIND}
    #logs.append({ "command": f"cmd {cmd}", "term": myTerm, "operationIND" : o})


def form_log_entry_message(entry):
    return raft_pb2.LogEntry(command=entry["command"], term=entry["term"], operationIND=entry["operationIND"])


def handle_leader():
    global timer, commitIndex, nextIndex, matchIndex, logs

    remove_this = False

    if timer % 1000 != 0:
        return

    timer = 0

    for key in servers:
        if key == id:
            continue

        #Send heartbeat loop
        while True:
            try:
                channel = grpc.insecure_channel(servers[key])
                stub = raft_pb2_grpc.RaftServiceStub(channel)
                prevLogIndex = nextIndex[key] - 1
                prevLogTerm = 0
                if logs and prevLogIndex != 0 and (prevLogIndex-1) < len(logs):
                    prevLogTerm = logs[prevLogIndex - 1]["term"]

                paramEntries = [form_log_entry_message(x) for x in logs[prevLogIndex:]]
                params = raft_pb2.AppendEntriesRequest(
                    leader=raft_pb2.TermLeaderIDPair(term=myTerm, leaderID=id),
                    prevLogIndex=prevLogIndex,
                    prevLogTerm=prevLogTerm,
                    leaderCommit=commitIndex,
                )
                params.entries.extend(paramEntries)
                response = stub.AppendEntries(params, timeout=0.10)
                term, result = response.result.term, response.result.verdict
            except grpc.RpcError:
                #key_to_be_kicked = key
                #remove_this = True
                break

            if result:
                nextIndex[key] = matchIndex[key] = prevLogIndex + len(paramEntries) + 1
                matchIndex[key] -= 1
                nextIndex[key] = max(nextIndex[key], 1)
                break

            if term > myTerm:
                invoke_term_change(term)
                return

            nextIndex[key] -= 1
            if nextIndex[key] == 0:
                nextIndex[key] = 1
                break

        #if remove_this:
            #break

    #if remove_this:
        #del servers[key_to_be_kicked]
        #remove_this = False

    while commitIndex < len(logs):
        newCommitIndex = commitIndex + 1
        reachable_servers = 1 + len(matchIndex)
        validServers = 1
        for key in matchIndex:
            if matchIndex[key] >= newCommitIndex:
                validServers += 1
        if validServers >= reachable_servers / 2:
            commitIndex = newCommitIndex
        else:
            break


def handle_current_state():
    apply_commits()
    if myState == "Follower":
        handle_follower()
    if myState == "Candidate":
        handle_candidate()
    elif myState == "Leader":
        handle_leader()


class ServerService(drone_pb2_grpc.ServerServicer):
    def __init__(self):
        self.channel = grpc.insecure_channel("update:50054")
        self.stub = drone_pb2_grpc.UpdateStub(self.channel)

    def SendCommand(self, request, context):
        cmd = request.text.strip().lower()
        success, error = update_log(cmd)

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

        
        if not success:
            return drone_pb2.Reply(text=f"Error: {error}")

        #return drone_pb2.Reply(text="Command acknowledged.")
        try:
            response = self.stub.SendCommand(
                drone_pb2.Command(text=cmd)
            )
            return response
        except Exception as e:
            return drone_pb2.Reply(
                text=f"Error communicating with update service: {str(e)}"
            )

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
    
    def ViewLog(self, request, context):
        response_logs = []

        for entry in logs:
            response_logs.append(
                raft_pb2.LogEntries(
                    op_command=entry["command"],
                    op_term=entry["term"],
                    operationIND=entry["operationIND"],
                )
            )

        return raft_pb2.LogResponse(logs=response_logs)
    
    def ResetLeader(self, request, context):
        leader_reset()
        return raft_pb2.LogRequest(ar=1)

    def SetVal(self, request):
        print("hi")
    def GetVal(self, request):
        print("hi")

def serve():
    global timer, suspended, myPort

    #port = int(os.environ.get("NODE_PORT", 50053))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    drone_pb2_grpc.add_ServerServicer_to_server(ServerService(), server)
    raft_pb2_grpc.add_RaftServiceServicer_to_server(ServerService(), server)
    server.add_insecure_port(myPort)
    server.start()
    print(f"Server running on {myPort}")

    
    while True:
        if suspended:
            server.stop(0)
            time.sleep(globalPeriod)
            server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
            drone_pb2_grpc.add_ServerServicer_to_server(ServerService(), server)
            raft_pb2_grpc.add_RaftServiceServicer_to_server(ServerService(), server)
            server.add_insecure_port(myPort)
            server.start()
            suspended = False

        #init_servers()
        handle_current_state()

        time.sleep(0.001)
        timer += 1
        



if __name__ == "__main__":
    startup()
    serve()