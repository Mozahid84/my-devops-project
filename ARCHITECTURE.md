# Architecture Diagrams

## 1. Overall System Architecture

```mermaid
graph TB
    subgraph DevOps["DevOps Workflow"]
        Dev["👤 Developer"]
        Git["📦 GitLab Repo"]
        CICD["🔄 GitLab CI/CD"]
    end
    
    subgraph Orchestration["Orchestration Layer"]
        AWX["🎛️ AWX Instance"]
        FastAPI["⚡ FastAPI Service"]
    end
    
    subgraph Network["Network & VMs"]
        Net["📡 Network"]
        VM1["🖥️ VM1 CentOS 8<br/>Primary"]
        VM2["🖥️ VM2 CentOS 8<br/>Secondary"]
    end
    
    subgraph Apps["Applications"]
        MSSQL1["🗄️ MSSQL 2019<br/>Instance 1"]
        MSSQL2["🗄️ MSSQL 2019<br/>Instance 2"]
        DB1["📊 AdventureWorks"]
        DB2["📊 AdventureWorks"]
    end
    
    Dev -->|push| Git
    Git -->|trigger| CICD
    CICD -->|provision| AWX
    CICD -->|provision| FastAPI
    
    AWX -->|ansible-playbook| Net
    FastAPI -->|ansible-runner| Net
    
    Net -->|target| VM1
    Net -->|target| VM2
    
    VM1 --> MSSQL1
    VM2 --> MSSQL2
    
    MSSQL1 --> DB1
    MSSQL2 --> DB2
    
    VM1 -->|backup 10x| Backup["💾 Backup Storage"]
    Backup -->|restore| VM2
    
    style Dev fill:#e1f5ff
    style Git fill:#fff3e0
    style CICD fill:#f3e5f5
    style AWX fill:#c8e6c9
    style FastAPI fill:#c8e6c9
    style VM1 fill:#ffccbc
    style VM2 fill:#ffccbc
    style Backup fill:#ffe0b2
```

## 2. Ansible Deployment Architecture

```mermaid
graph LR
    subgraph Ansible["Ansible Control Machine"]
        Play["📋 Playbook<br/>site.yml"]
        Role["🔧 mssql Role"]
        Inv["📝 Inventory"]
    end
    
    subgraph Tasks["Task Execution"]
        T1["📥 Install"]
        T2["⚙️ Configure"]
        T3["📊 Database"]
        T4["💾 Backup"]
        T5["↩️ Restore"]
    end
    
    subgraph Targets["Target Servers"]
        V1["VM1<br/>Primary"]
        V2["VM2<br/>Secondary"]
    end
    
    Play --> Role
    Role --> T1
    T1 --> T2
    T2 --> T3
    T3 --> T4
    T4 --> T5
    
    Play --> Inv
    Inv --> V1
    Inv --> V2
    
    T1 -.->|on both| V1
    T1 -.->|on both| V2
    T2 -.->|on both| V1
    T2 -.->|on both| V2
    T3 -.->|on both| V1
    T3 -.->|on both| V2
    T4 -.->|on VM1| V1
    T5 -.->|on VM2| V2
    
    style Play fill:#fff9c4
    style Role fill:#c5e1a5
    style T1 fill:#b2dfdb
    style T4 fill:#b2dfdb
    style T5 fill:#b2dfdb
    style V1 fill:#ffccbc
    style V2 fill:#ffccbc
```

## 3. FastAPI Deployment Service Architecture

```mermaid
graph TB
    subgraph Client["Client Layer"]
        Web["🌐 Web Browser"]
        CLI["💻 CLI/curl"]
        App["📱 Application"]
    end
    
    subgraph FastAPI["FastAPI Server"]
        Router["🛣️ Routers"]
        Deploy["🚀 Deploy Routes"]
        Health["❤️ Health Routes"]
        Logs["📝 Log Routes"]
        Runner["🎯 AnsibleRunner"]
    end
    
    subgraph Background["Background Processing"]
        Queue["📦 Task Queue"]
        Tasks["⚙️ Background Tasks"]
    end
    
    subgraph Ansible["Ansible Execution"]
        Playbook["📋 Playbook Runner"]
        Inventory["📝 Inventory"]
    end
    
    subgraph Targets["Target Infrastructure"]
        V1["🖥️ VM1"]
        V2["🖥️ VM2"]
    end
    
    Web -->|HTTP| Router
    CLI -->|HTTP| Router
    App -->|HTTP| Router
    
    Router --> Deploy
    Router --> Health
    Router --> Logs
    
    Deploy --> Queue
    Health --> Runner
    Logs --> Runner
    
    Queue --> Tasks
    Tasks --> Runner
    Runner --> Playbook
    Runner --> Inventory
    
    Playbook --> Ansible
    Inventory --> Ansible
    
    Ansible --> V1
    Ansible --> V2
    
    style Web fill:#e1f5ff
    style CLI fill:#e1f5ff
    style App fill:#e1f5ff
    style Router fill:#fff9c4
    style Deploy fill:#f8bbd0
    style Health fill:#c8e6c9
    style Logs fill:#c8e6c9
    style Runner fill:#ffccbc
    style Queue fill:#ffe0b2
    style Tasks fill:#ffe0b2
```

## 4. Backup and Restore Data Flow

```mermaid
graph LR
    subgraph VM1Backup["VM1: Backup Creation"]
        DB1["🗄️ AdventureWorks<br/>Database"]
        Backup["💾 10x Striped Backup<br/>adv_stripe_01-10.bak"]
        Dir1["📁 /backup/striped/"]
    end
    
    subgraph Transfer["Transfer Layer"]
        Fetch["📥 Fetch<br/>ansible module"]
        Local["💻 Control Machine<br/>./backups/vm1_striped/"]
        Copy["📤 Copy<br/>ansible module"]
    end
    
    subgraph VM2Restore["VM2: Restore Operation"]
        Dir2["📁 /backup/striped/"]
        Restore["↩️ RESTORE DATABASE<br/>from 10x striped"]
        DB2["🗄️ AdventureWorks<br/>Database"]
    end
    
    DB1 -->|BACKUP to| Backup
    Backup --> Dir1
    Dir1 -->|fetch| Fetch
    Fetch --> Local
    Local -->|copy| Copy
    Copy --> Dir2
    Dir2 -->|RESTORE from| Restore
    Restore --> DB2
    
    style DB1 fill:#c8e6c9
    style Backup fill:#ffe0b2
    style Fetch fill:#81c784
    style Local fill:#ffb74d
    style Copy fill:#81c784
    style Restore fill:#81c784
    style DB2 fill:#c8e6c9
```

## 5. Request/Response Flow - API Call

```mermaid
sequenceDiagram
    participant Client as 🖥️ Client
    participant API as ⚡ FastAPI API
    participant Queue as 📦 Task Queue
    participant Ansible as 🎯 Ansible
    participant Target as 🖥️ Target VMs
    
    Client->>API: POST /deploy/install
    API->>Queue: Add background task
    API-->>Client: 202 Accepted
    
    Note over Client: Returns immediately
    
    Queue->>Ansible: Execute playbook
    Ansible->>Target: Run tasks
    Target-->>Ansible: Task output
    Ansible-->>Queue: Execution complete
    Queue->>API: Store in history
    
    Note over Client: Client polls for status
    Client->>API: GET /logs/latest
    API-->>Client: Current logs
    
    Client->>API: GET /deploy/history
    API-->>Client: Execution status
    
    alt Deployment Complete
        API-->>Client: status: success ✓
    else Still Running
        API-->>Client: status: running ⏳
        Note over Client: Poll again in 10 seconds
    end
```

## 6. Deployment Task Execution Sequence

```mermaid
graph TD
    Start["🚀 Start Deployment"] --> Phase1["📥 Phase 1: Install"]
    Phase1 --> T1a["Install dependencies"]
    T1a --> T1b["Add Microsoft repos"]
    T1b --> T1c["Install MSSQL Server"]
    T1c --> T1d["Install MSSQL Tools"]
    T1d --> T1e["Run MSSQL setup"]
    T1e --> T1f["Start service"]
    T1f --> Phase2["⚙️ Phase 2: Configure"]
    
    Phase2 --> T2a["Create directories"]
    T2a --> T2b["Set default paths"]
    T2b --> T2c["Configure network"]
    T2c --> T2d["Enable SQL Agent"]
    T2d --> Phase3["📊 Phase 3: Database"]
    
    Phase3 --> T3a["Download AdventureWorks"]
    T3a --> T3b["Restore database"]
    T3b --> T3c["Verify database"]
    T3c --> Decision{"Which VM?"}
    
    Decision -->|VM1| Phase4["💾 Phase 4: Backup"]
    Decision -->|VM2| Skip1["⏭️ Skip Backup"]
    
    Phase4 --> T4a["Create backup dir"]
    T4a --> T4b["Create 10x striped backup"]
    T4b --> T4c["Verify backup files"]
    T4c --> Phase5["↩️ Phase 5: Restore"]
    
    Skip1 --> Phase5
    
    Phase5 --> T5a["Fetch backups from VM1"]
    T5a --> T5b["Copy to VM2"]
    T5b --> T5c["Restore from stripes"]
    T5c --> T5d["Verify restore"]
    T5d --> End["✅ Complete"]
    
    style Start fill:#c8e6c9
    style Phase1 fill:#b2dfdb
    style Phase2 fill:#b2ebee
    style Phase3 fill:#b3e5fc
    style Phase4 fill:#ffe0b2
    style Phase5 fill:#ffcc80
    style End fill:#a5d6a7
    style Decision fill:#fff9c4
```

## 7. Health Check Flow

```mermaid
graph TD
    Start["🏥 Health Check<br/>GET /health/ready"] --> C1["✓ Ansible<br/>Installed?"]
    C1 -->|No| Fail1["❌ FAIL:<br/>Ansible not found"]
    C1 -->|Yes| C2["✓ Inventory<br/>File exists?"]
    
    C2 -->|No| Fail2["❌ FAIL:<br/>Inventory missing"]
    C2 -->|Yes| C3["✓ Disk Space<br/>≥ 5GB?"]
    
    C3 -->|No| Fail3["❌ FAIL:<br/>Insufficient space"]
    C3 -->|Yes| C4["✓ CPU<br/>< 90%?"]
    
    C4 -->|No| Warn1["⚠️ WARN:<br/>CPU high"]
    C4 -->|Yes| C5["✓ Memory<br/>< 90%?"]
    
    C5 -->|No| Warn2["⚠️ WARN:<br/>Memory high"]
    C5 -->|Yes| Success["✅ READY:<br/>All checks pass"]
    
    Fail1 --> Overall["📊 Overall<br/>Status"]
    Fail2 --> Overall
    Fail3 --> Overall
    Warn1 --> Overall
    Warn2 --> Overall
    Success --> Overall
    
    Overall -->|Any FAIL| Red["🔴 Ready: FALSE"]
    Overall -->|All PASS| Green["🟢 Ready: TRUE"]
    
    style Start fill:#e1f5ff
    style Success fill:#c8e6c9
    style Green fill:#66bb6a
    style Red fill:#ef5350
    style Fail1 fill:#ffcdd2
    style Fail2 fill:#ffcdd2
    style Fail3 fill:#ffcdd2
    style Warn1 fill:#ffe0b2
    style Warn2 fill:#ffe0b2
```

## 8. Configuration Management Hierarchy

```mermaid
graph TB
    subgraph Priority["Priority Order<br/>Highest to Lowest"]
        L1["1️⃣ CLI Arguments<br/>ansible-playbook -e var=value"]
        L2["2️⃣ Host Variables<br/>host_vars/vm1.yml"]
        L3["3️⃣ Group Variables<br/>group_vars/mssql_servers.yml"]
        L4["4️⃣ Role Defaults<br/>roles/mssql/defaults/main.yml"]
    end
    
    Example1["🔹 sa_password<br/>CLI override"]
    Example2["🔹 instance_name<br/>From host_vars"]
    Example3["🔹 mssql_version<br/>From group_vars"]
    Example4["🔹 mssql_port<br/>From defaults"]
    
    L1 --> Example1
    L2 --> Example2
    L3 --> Example3
    L4 --> Example4
    
    Result["📋 Final Configuration<br/>Merged from hierarchy"]
    
    Example1 --> Result
    Example2 --> Result
    Example3 --> Result
    Example4 --> Result
    
    Result --> VM1["🖥️ VM1<br/>instance1"]
    Result --> VM2["🖥️ VM2<br/>instance2"]
    
    style L1 fill:#ffcdd2
    style L2 fill:#ffe0b2
    style L3 fill:#c8e6c9
    style L4 fill:#b3e5fc
    style Result fill:#f0f4c3
```

## 9. Error Handling Flow

```mermaid
graph TD
    Task["⚙️ Execute Task"] --> Try["🔄 Try Execution"]
    Try -->|Success| Pass["✅ Success"]
    Try -->|Exception| Catch["🛑 Catch Error"]
    
    Catch --> Type{"Error Type?"}
    
    Type -->|Timeout| Retry["🔁 Retry Logic<br/>Up to 3 times"]
    Type -->|Network| Retry
    Type -->|Other| Fatal["💥 Fatal Error"]
    
    Retry --> Attempt{"Retry<br/>Successful?"}
    Attempt -->|Yes| Pass
    Attempt -->|No| Fatal
    
    Pass --> Record1["📝 Log: SUCCESS"]
    Fatal --> Record2["📝 Log: FAILED"]
    
    Record1 --> History["📊 Store in<br/>Execution History"]
    Record2 --> History
    
    History --> Response["📤 Return to Client"]
    
    style Task fill:#fff9c4
    style Try fill:#b3e5fc
    style Pass fill:#c8e6c9
    style Catch fill:#ffcdd2
    style Fatal fill:#ef5350
    style Retry fill:#ffe0b2
    style History fill:#b39ddb
    style Response fill:#a5d6a7
```

## 10. VM Connectivity Verification

```mermaid
graph LR
    API["⚡ FastAPI<br/>POST /deploy/ping"] --> Cmd["⌨️ Build Command<br/>ansible all -i inventory -m ping"]
    Cmd --> Exec["🚀 Execute<br/>subprocess.run"]
    Exec --> SSH1["🔑 SSH to VM1"]
    Exec --> SSH2["🔑 SSH to VM2"]
    
    SSH1 -->|Success| Pong1["🔔 PONG<br/>VM1 alive"]
    SSH1 -->|Failure| Fail1["❌ VM1<br/>unreachable"]
    
    SSH2 -->|Success| Pong2["🔔 PONG<br/>VM2 alive"]
    SSH2 -->|Failure| Fail2["❌ VM2<br/>unreachable"]
    
    Pong1 --> Result{"All<br/>Connected?"}
    Pong2 --> Result
    Fail1 --> Result
    Fail2 --> Result
    
    Result -->|Yes| Response["📤 Response<br/>status: success"]
    Result -->|No| Response2["📤 Response<br/>status: failed"]
    
    Response --> Client["🖥️ Client"]
    Response2 --> Client
    
    style API fill:#fff9c4
    style Cmd fill:#b3e5fc
    style Exec fill:#b2dfdb
    style SSH1 fill:#c8e6c9
    style SSH2 fill:#c8e6c9
    style Pong1 fill:#a5d6a7
    style Pong2 fill:#a5d6a7
    style Fail1 fill:#ef5350
    style Fail2 fill:#ef5350
    style Response fill:#c5e1a5
```
