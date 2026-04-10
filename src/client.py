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

def find_leader():
    global current_leader, servers
    while 1:
        for addr in servers:
            try:
                channel = grpc.insecure_channel(servers[addr])
                stub = raft_pb2_grpc.RaftServiceStub(channel)

                response = stub.GetLeader(raft_pb2.Empty(), timeout=0.2)

                current_leader = response.nodeAddress
                print(f"[Client] New leader: {current_leader}")
                #channel2 = grpc.insecure_channel(servers[current_leader])
                #stub2 = raft_pb2_grpc.RaftServiceStub(channel2)
                #stub3 = drone_pb2_grpc.ServerStub(channel2)
                stub2 = stub
                stub3 = drone_pb2_grpc.ServerStub(channel)
                #response2 = stub2.GetLeader(raft_pb2.Empty(), timeout=0.2)
                return stub3, stub2

            except grpc.RpcError:
                continue
        time.sleep(0.2)


def init_servers():
    global servers
    servers = {}
    with open("config2.conf", "r") as f:
        for line in f:
            parts = line.split(" ")
            servers[int(parts[0])] = f'{parts[1]}:{parts[2].rstrip()}'

def add_node_to_cluster(stub, node_id, node_address):
    try:
        #channel = grpc.insecure_channel(TARGET)
        channel2 = grpc.insecure_channel(node_address)
        temp_stub = raft_pb2_grpc.RaftServiceStub(channel2)
        #raft_stub = raft_pb2_grpc.RaftServiceStub(channel)
        response2 = temp_stub.ResetLeader(raft_pb2.LogRequest(ar=1))
        response = stub.AddNode(
            raft_pb2.AddNodeRequest(nodeId=node_id, nodeAddress=node_address)
        )
        servers[node_id] = node_address
        print(f"AddNode response: {response.message}")
    except Exception as e:
        print(f"Failed to add node: {e}")


def measure_latency(stub, iterations=500):
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
    count = 0
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
    print(f"\n--- Stress Test ({clients} clients, {duration}s) ---")

    def worker():
        channel = grpc.insecure_channel(TARGET)
        stub = drone_pb2_grpc.ServerStub(channel)
        end_time = time.time() + duration
        count = 0
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
                response = stub2.GetLeader(raft_pb2.Empty(), timeout=0.2)
            except grpc.RpcError:
                stub, stub2 = find_leader()
                continue
            measure_latency(stub, n)
            continue

        if cmd.startswith("throughput"):
            parts = cmd.split()
            sec = int(parts[1]) if len(parts) > 1 else 10
            try:
                response = stub2.GetLeader(raft_pb2.Empty(), timeout=0.2)
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
                response = stub2.GetLeader(raft_pb2.Empty(), timeout=0.2)
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
                    response = stub2.GetLeader(raft_pb2.Empty(), timeout=0.2)
                except grpc.RpcError:
                    stub, stub2 = find_leader()
                    continue
                add_node_to_cluster(stub2, int(parts[1]), parts[2])
            continue

        if cmd.startswith("log"):
            stub3, stub4 = find_leader()
            response = stub4.ViewLog(raft_pb2.LogRequest(ar=1))
            for log in response.logs:
                print(log.op_command, log.op_term, log.operationIND)

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
    channel = grpc.insecure_channel(TARGET)
    stub = drone_pb2_grpc.ServerStub(channel)
    stub2 = raft_pb2_grpc.RaftServiceStub(channel)
    interactive_loop(stub, stub2)


if __name__ == "__main__":
    init_servers()
    main()