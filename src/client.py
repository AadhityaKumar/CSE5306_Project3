import time
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor
import grpc
import drone_pb2
import drone_pb2_grpc
import raft_pb2
import raft_pb2_grpc

TARGET = "server:50053"
servers = {}
current_leader = None


def init_servers():
    global servers
    servers = {}
    with open("config2.conf", "r") as f:
        for line in f:
            parts = line.split(" ")
            servers[int(parts[0])] = f'{parts[1]}:{parts[2].rstrip()}'


def find_leader():
    global current_leader, servers
    while True:
        for addr in servers:
            try:
                channel = grpc.insecure_channel(servers[addr])
                stub2 = raft_pb2_grpc.RaftServiceStub(channel)
                response = stub2.GetLeader(raft_pb2.Empty(), timeout=0.2)
                current_leader = response.nodeAddress
                print(f"[Client] New leader: {current_leader}")
                stub = drone_pb2_grpc.ServerStub(channel)
                return stub, stub2
            except grpc.RpcError:
                continue
        time.sleep(0.2)


def add_node_to_cluster(stub, node_id, node_address):
    try:
        channel2 = grpc.insecure_channel(node_address)
        temp_stub = raft_pb2_grpc.RaftServiceStub(channel2)
        temp_stub.ResetLeader(raft_pb2.LogRequest(ar=1))
        response = stub.AddNode(
            raft_pb2.AddNodeRequest(nodeId=node_id, nodeAddress=node_address)
        )
        servers[node_id] = node_address
        print(f"AddNode response: {response.message}")
    except Exception as e:
        print(f"Failed to add node: {e}")


def measure_latency(stub, iterations=500):
    """Measure RPC latency over a number of iterations."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        stub.SendCommand(drone_pb2.Command(text="sensor voltage"))
        end = time.perf_counter()
        times.append((end - start) * 1000)
    print("\n--- Latency Benchmark ---")
    print(f"Samples: {iterations}")
    print(f"Avg: {statistics.mean(times):.2f} ms")
    print(f"StdDev: {statistics.stdev(times):.2f} ms")
    print(f"Min: {min(times):.2f} ms")
    print(f"Max: {max(times):.2f} ms")
    print(f"P95: {sorted(times)[int(0.95 * len(times))]:.2f} ms")
    print("--------------------------\n")


def measure_throughput(stub, duration=10):
    """Measure requests per second over a given duration."""
    count    = 0
    end_time = time.time() + duration
    while time.time() < end_time:
        stub.SendCommand(drone_pb2.Command(text="sensor voltage"))
        count += 1
    print("\n--- Throughput Test ---")
    print(f"Duration: {duration} sec")
    print(f"Total Requests: {count}")
    print(f"Requests/sec: {count/duration:.2f}")
    print("------------------------\n")


def stress_test(clients=5, duration=10):
    """Run concurrent clients hammering the server simultaneously."""
    print(f"\n--- Stress Test ({clients} clients, {duration}s) ---")

    def worker():
        channel  = grpc.insecure_channel(TARGET)
        stub     = drone_pb2_grpc.ServerStub(channel)
        end_time = time.time() + duration
        count    = 0
        while time.time() < end_time:
            stub.SendCommand(drone_pb2.Command(text="sensor voltage"))
            count += 1
        return count

    with ThreadPoolExecutor(max_workers=clients) as executor:
        results = list(executor.map(lambda _: worker(), range(clients)))

    total = sum(results)
    print(f"Total Requests: {total}")
    print(f"Aggregate Requests/sec: {total/duration:.2f}")
    print("-------------------------------\n")


def interactive_loop(stub, stub2):
    print("Type 'help' for commands.")
    print("Benchmark commands:")
    print("  benchmark <iterations>")
    print("  throughput <seconds>")
    print("  stress <clients> <seconds>\n")

    while True:
        cmd = input("> ").strip()

        if cmd.startswith("benchmark"):
            parts = cmd.split()
            n = int(parts[1]) if len(parts) > 1 else 500
            try:
                stub2.GetLeader(raft_pb2.Empty(), timeout=0.2)
            except grpc.RpcError:
                stub, stub2 = find_leader()
                continue
            measure_latency(stub, n)
            continue

        if cmd.startswith("throughput"):
            parts = cmd.split()
            sec = int(parts[1]) if len(parts) > 1 else 10
            try:
                stub2.GetLeader(raft_pb2.Empty(), timeout=0.2)
            except grpc.RpcError:
                stub, stub2 = find_leader()
                continue
            measure_throughput(stub, sec)
            continue

        if cmd.startswith("stress"):
            parts = cmd.split()
            clients = int(parts[1]) if len(parts) > 1 else 5
            sec = int(parts[2]) if len(parts) > 2 else 10
            try:
                stub2.GetLeader(raft_pb2.Empty(), timeout=0.2)
            except grpc.RpcError:
                stub, stub2 = find_leader()
                continue
            stress_test(clients, sec)
            continue

        if cmd.startswith("addnode"):
            parts = cmd.split()
            if len(parts) != 3:
                print("Usage: addnode <id> <host:port>")
            else:
                try:
                    stub2.GetLeader(raft_pb2.Empty(), timeout=0.2)
                except grpc.RpcError:
                    stub, stub2 = find_leader()
                    continue
                add_node_to_cluster(stub2, int(parts[1]), parts[2])
            continue

        if cmd == "getleader":
            try:
                response = stub2.GetLeader(raft_pb2.Empty(), timeout=0.2)
                if response.nodeId == -1:
                    print("No leader elected yet")
                else:
                    print(f"Leader: Node {response.nodeId} at {response.nodeAddress}")
            except grpc.RpcError:
                print("Could not reach any node — finding leader...")
                stub, stub2 = find_leader()
            continue

        if cmd.startswith("suspend"):
            parts = cmd.split()
            if len(parts) != 3:
                print("Usage: suspend <host:port> <seconds>")
            else:
                try:
                    channel = grpc.insecure_channel(parts[1])
                    temp_stub = raft_pb2_grpc.RaftServiceStub(channel)
                    temp_stub.Suspend(raft_pb2.SuspendRequest(period=int(parts[2])))
                    print(f"Node at {parts[1]} suspended for {parts[2]} seconds")
                except grpc.RpcError as e:
                    print(f"Failed to suspend node: {e}")
            continue

        if cmd.startswith("log"):
            stub, stub2 = find_leader()
            response = stub2.ViewLog(raft_pb2.LogRequest(ar=1))
            if not response.logs:
                print("Log is empty")
            for log in response.logs:
                print(f"command: {log.op_command}  term: {log.op_term}  index: {log.operationIND}")
            continue

        if cmd == "quit":
            break

        start = time.perf_counter()
        try:
            response = stub.SendCommand(drone_pb2.Command(text=cmd))
        except grpc.RpcError:
            stub, stub2 = find_leader()
            continue
        end = time.perf_counter()

        print(f"[Latency: {(end - start)*1000:.2f} ms]")
        print(response.text)


def main():
    """Connect to server and start interactive loop."""
    channel = grpc.insecure_channel(TARGET)
    stub = drone_pb2_grpc.ServerStub(channel)
    stub2 = raft_pb2_grpc.RaftServiceStub(channel)
    interactive_loop(stub, stub2)


if __name__ == "__main__":
    init_servers()
    main()