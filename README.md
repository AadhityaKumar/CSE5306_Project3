# Distributed Drone Telemetry System  
CSE 5306 – Project 2  
gRPC + Docker Compose

GITHUB LINK: https://github.com/AadhityaKumar/CSE5306_Project3.git
- CODE IN THE MASTER BRANCH

---

# 1. Overview

This project implements a distributed drone telemetry processing pipeline using:

- Python 3.11  
- gRPC  
- Docker Compose  

The system simulates multiple independent sensor services that generate telemetry data and alert conditions. Telemetry flows through a multi-stage processing pipeline before reaching an interactive client interface.

Two architectures are implemented:

1. Distributed Microservices Architecture
2. Monolithic Architecture (Single Container)

Both architectures expose the same gRPC interface to ensure functional equivalence and allow direct performance comparison.

This project has been edited to include 2PC and the RAFT consensus algorithm.

---

# 2. System Architecture

## Distributed Telemetry Flow

Sensors → Aggregation → Analysis → Update → Server → Client  

Command Flow:

Client ↔ Server ↔ Update  

Each stage runs inside its own Docker container and communicates via gRPC.

---

## Monolithic Architecture

All telemetry generation and processing logic runs inside a single container.

This removes inter-container RPC overhead while preserving identical client functionality.

---

# 3. Project Structure

src/
  - aggregation.py
  - analysis.py
  - update.py
  - server.py
  - client.py
  - monolith.py
  - imu_sensor.py
  - gps_sensor.py
  - engine_sensor.py
  - battery_sensor.py
  - airdata_sensor.py
  - drone.proto
  - drone_pb2.py
  - drone_pb2_grpc.py
  - config.conf
  - raft_pb2.py
  - raft_pb2_grpc.py
  - tpc.proto
  - tpc_pb2.py
  - tpc_pb2_grpc.py
  - coordinator.py
  - participant.py
  - tpc_client.py

Dockerfiles/
  - Dockerfile.airdata
  - Dockerfile.battery
  - Dockerfile.engine
  - Dockerfile.gps
  - Dockerfile.imu
  - Dockerfile.aggregation
  - Dockerfile.analysis
  - Dockerfile.update
  - Dockerfile.server
  - Dockerfile.client
  - Dockerfile.monolith
  - Dockerfile.tpc_coordinator
  - Dockerfile.tpc_participant
  - Dockerfile.tpc_client

docker-compose.yml

run_distributed.sh

run_monolith.sh

README.md

All Python source files reside in `src/`.

---

# 4. Running the System

Run all commands from the project root (where docker-compose.yml is located).

Docker Compose profiles are used to isolate architectures.

---

## 🔵 Run Distributed Architecture

./run_distributed.sh

Equivalent manual commands:

docker compose down -v --remove-orphans
docker compose --profile distributed up -d --build
docker compose run --rm client

---

## 🟣 Run Monolithic Architecture

./run_monolith.sh

Equivalent manual commands:

docker compose down -v --remove-orphans
docker compose --profile monolith up -d --build
docker compose run --rm client

---

## 🔄 Switching Architectures

No manual cleanup required.

Each run script automatically executes:

docker compose down -v --remove-orphans

Important:
Both architectures bind to port 50053.  
Do NOT attempt to run them simultaneously.

---

# 5. Available Client Commands

help  
  Displays available commands.

status  
  Displays system status.

health  
  Displays overall health (based on alerts).

list  
  Lists available sensor names.

sensor <name>  
  Displays current value for a specific sensor.

alerts  
  Displays all currently active alerts.

benchmark latency <samples>  
  Runs latency benchmark using <samples> RPC calls.

benchmark throughput <seconds>  
  Runs throughput benchmark for <seconds>.

benchmark stress <clients> <seconds>  
  Runs concurrency stress test using <clients> for <seconds>.

quit  
  Exits the client.

### Sensor Names

- altitude
- airspeed
- voltage
- egt
- latitude
- longitude
- vibration

Example:

sensor voltage

---

# 6. Units Used

| Sensor     | Units |
|------------|-------|
| altitude   | ft    |
| airspeed   | kt    |
| voltage    | V     |
| egt        | °C    |
| latitude   | deg   |
| longitude  | deg   |
| vibration  | g     |

---

# 7. Benchmarking

Run benchmarks while inside the client.

Latency test (example):

benchmark latency 2000

Throughput test:

benchmark throughput 10
benchmark throughput 30

Concurrency stress test:

benchmark stress 5 15
benchmark stress 20 20

---

# 8. Docker Resource Monitoring

While the system is running in another terminal:

docker stats

This displays:

- CPU usage
- Memory usage
- Network I/O
- Container resource consumption

Stop monitoring with Ctrl + C.

---

# 9. Performance Comparison Summary

Distributed Architecture:
- Service isolation
- Modular design
- RPC chaining overhead
- Centralized pipeline stages

Monolithic Architecture:
- No inter-container serialization
- Reduced RPC overhead
- Single failure domain
- Lower architectural separation

---

# 10. Troubleshooting

Make scripts executable:

chmod +x run_distributed.sh
chmod +x run_monolith.sh

Check running containers:

docker ps

Force shutdown everything:

docker compose down -v --remove-orphans

---

# 11. RAFT

To view output of a server node, in another terminal:

Go to the project3 directory while running and type "docker compose --profile distributed logs -f (node-name)"

For example, to view the output of server 1, type "docker compose --profile distributed logs -f server1"


To suspend a node:

In client, type "suspend (server-name) (seconds)

For example, in order to suspend server 1 for 10 seconds, type "suspend server1:50055 10".


To add a node during runtime:

First, remove the node to be added during runtime from config.conf.

Run the project, and type "addnode (node-id) (server-name)" in the client.

For example, to add server 4 during runtime, first remove it from config.conf, run, then type "addnode 4 server4:50058".


To view the log:

Type "log" into the client

---

# 12. 2PC

To start 2PC on the system use "docker compose --profile tpc up --build"

The system will automatically run a full 2PC round on startup. The tpc-client container triggers a transaction, the coordinator broadcasts vote requests to all 5 participants, collects votes, and sends a global commit or abort decision.

To stop: "docker compose --profile tpc down -v --remove-orphans"

You are able to run commands in another terminal while viewing the system's output by running this command in another terminal: "docker attach cse5306_project3-client-1"

You can then run commands like:

"getleader" - Shows the current Raft leader node and address

"suspend <host:port> <seconds>" - Suspends a node for a given period to simulate failure

"sensor <name>" - Gets current telemetry value (ex. sensor voltage)

"quit" - Exits the client


---

# 13. Notes

- Do not run distributed and monolith simultaneously.
- Always switch using provided scripts.
- Ensure port 50053 is free before starting either architecture.
- Benchmarks should be run with minimal host background load for accurate results.
- Do not run profiles simultaneously. The distributed and tpc profiles use overlapping port ranges.
- Attaching to the client - the client container must be attached from a separate terminal window while the cluster is running in another.

---

# 14. Resources

https://raft.github.io/raft.pdf

https://thesecretlivesofdata.com/raft/

https://vamsi995.github.io/projects/Raft/

https://www.geeksforgeeks.org/dbms/two-phase-commit-protocol-distributed-transaction-management/

Other sources, such as ChatGPT, for help:
- documentation
- debugging docker + python code
- structure questions


