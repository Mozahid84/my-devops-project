# Architecture Diagrams

## 1. Overall System Architecture

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"transparent","primaryColor":"#1e293b","primaryTextColor":"#f8fafc","primaryBorderColor":"#38bdf8","lineColor":"#94a3b8","secondaryColor":"#064e3b","tertiaryColor":"#312e81","clusterBkg":"#0f172a","clusterBorder":"#475569","edgeLabelBackground":"#111827","fontFamily":"Inter, Segoe UI, Arial, sans-serif","textColor":"#f8fafc","mainBkg":"#111827","nodeBorder":"#38bdf8"}}}%%
graph TB
    subgraph DevOps["DevOps Workflow"]
        Dev["ðŸ‘¤ Developer"]
        Git["ðŸ“¦ GitLab Repo"]
        CICD["ðŸ”„ GitLab CI/CD"]
    end
    
    subgraph Orchestration["Orchestration Layer"]
        AWX["ðŸŽ›ï¸ AWX Instance"]
        FastAPI["âš¡ FastAPI Service"]
    end
    
    subgraph Network["Network & VMs"]
        Net["ðŸ“¡ Network"]
        VM1["ðŸ–¥ï¸ VM1 CentOS 8<br/>Primary"]
        VM2["ðŸ–¥ï¸ VM2 CentOS 8<br/>Secondary"]
    end
    
    subgraph Apps["Applications"]
        MSSQL1["ðŸ—„ï¸ MSSQL 2019<br/>Instance 1"]
        MSSQL2["ðŸ—„ï¸ MSSQL 2019<br/>Instance 2"]
        DB1["ðŸ“Š AdventureWorks"]
        DB2["ðŸ“Š AdventureWorks"]
    end
    
    Dev -->|push| Git
    Git -->|trigger| CICD
    CICD -->|provision| AWX
    CICD -->|provision| FastAPI
    
    AWX -->|ansible-playbook| Net
    FastAPI -->|Python SSH| Net
    
    Net -->|target| VM1
    Net -->|target| VM2
    
    VM1 --> MSSQL1
    VM2 --> MSSQL2
    
    MSSQL1 --> DB1
    MSSQL2 --> DB2
    
    VM1 -->|backup 10x| Backup["ðŸ’¾ Backup Storage"]
    Backup -->|restore| VM2
    
    style Dev fill:#0c4a6e,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    style Git fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc
    style CICD fill:#4c1d95,stroke:#a78bfa,stroke-width:2px,color:#f8fafc
    style AWX fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style FastAPI fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style VM1 fill:#7f1d1d,stroke:#f87171,stroke-width:2px,color:#f8fafc
    style VM2 fill:#7f1d1d,stroke:#f87171,stroke-width:2px,color:#f8fafc
    style Backup fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc
```

## 2. Ansible Deployment Architecture

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"transparent","primaryColor":"#1e293b","primaryTextColor":"#f8fafc","primaryBorderColor":"#38bdf8","lineColor":"#94a3b8","secondaryColor":"#064e3b","tertiaryColor":"#312e81","clusterBkg":"#0f172a","clusterBorder":"#475569","edgeLabelBackground":"#111827","fontFamily":"Inter, Segoe UI, Arial, sans-serif","textColor":"#f8fafc","mainBkg":"#111827","nodeBorder":"#38bdf8"}}}%%
graph LR
    subgraph Ansible["Ansible Control Machine"]
        Play["ðŸ“‹ Playbook<br/>site.yml"]
        Role["ðŸ”§ mssql Role"]
        Inv["ðŸ“ Inventory"]
    end
    
    subgraph Tasks["Task Execution"]
        T1["ðŸ“¥ Install"]
        T2["âš™ï¸ Configure"]
        T3["ðŸ“Š Database"]
        T4["ðŸ’¾ Backup"]
        T5["â†©ï¸ Restore"]
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
    
    style Play fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc
    style Role fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style T1 fill:#0c4a6e,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    style T4 fill:#0c4a6e,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    style T5 fill:#0c4a6e,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    style V1 fill:#7f1d1d,stroke:#f87171,stroke-width:2px,color:#f8fafc
    style V2 fill:#7f1d1d,stroke:#f87171,stroke-width:2px,color:#f8fafc
```

## 3. FastAPI Deployment Service Architecture

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"transparent","primaryColor":"#1e293b","primaryTextColor":"#f8fafc","primaryBorderColor":"#38bdf8","lineColor":"#94a3b8","secondaryColor":"#064e3b","tertiaryColor":"#312e81","clusterBkg":"#0f172a","clusterBorder":"#475569","edgeLabelBackground":"#111827","fontFamily":"Inter, Segoe UI, Arial, sans-serif","textColor":"#f8fafc","mainBkg":"#111827","nodeBorder":"#38bdf8"}}}%%
graph TB
    subgraph Client["Client Layer"]
        Web["ðŸŒ Web Browser"]
        CLI["ðŸ’» CLI/curl"]
        App["ðŸ“± Application"]
    end
    
    subgraph FastAPI["FastAPI Server"]
        Router["ðŸ›£ï¸ Routers"]
        Deploy["ðŸš€ Deploy Routes"]
        Health["â¤ï¸ Health Routes"]
        Logs["ðŸ“ Log Routes"]
        Runner["ðŸŽ¯ PythonDeployer"]
    end
    
    subgraph Background["Background Processing"]
        Queue["ðŸ“¦ Task Queue"]
        Tasks["âš™ï¸ Background Tasks"]
    end
    
    subgraph PythonSSH["Python SSH Execution"]
        SSH["ðŸ”‘ Paramiko SSH/SFTP"]
        Commands["âŒ¨ï¸ MSSQL Commands"]
    end
    
    subgraph Targets["Target Infrastructure"]
        V1["ðŸ–¥ï¸ VM1"]
        V2["ðŸ–¥ï¸ VM2"]
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
    Runner --> SSH
    SSH --> Commands
    
    Commands --> V1
    Commands --> V2
    
    style Web fill:#0c4a6e,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    style CLI fill:#0c4a6e,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    style App fill:#0c4a6e,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    style Router fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc
    style Deploy fill:#7f1d1d,stroke:#f87171,stroke-width:2px,color:#f8fafc
    style Health fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style Logs fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style Runner fill:#7f1d1d,stroke:#f87171,stroke-width:2px,color:#f8fafc
    style Queue fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc
    style Tasks fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc
```

## 4. Backup and Restore Data Flow

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"transparent","primaryColor":"#1e293b","primaryTextColor":"#f8fafc","primaryBorderColor":"#38bdf8","lineColor":"#94a3b8","secondaryColor":"#064e3b","tertiaryColor":"#312e81","clusterBkg":"#0f172a","clusterBorder":"#475569","edgeLabelBackground":"#111827","fontFamily":"Inter, Segoe UI, Arial, sans-serif","textColor":"#f8fafc","mainBkg":"#111827","nodeBorder":"#38bdf8"}}}%%
graph LR
    subgraph VM1Backup["VM1: Backup Creation"]
        DB1["ðŸ—„ï¸ AdventureWorks<br/>Database"]
        Backup["ðŸ’¾ 10x Striped Backup<br/>adv_stripe_01-10.bak"]
        Dir1["ðŸ“ /backup/striped/"]
    end
    
    subgraph Transfer["Transfer Layer"]
        Fetch["ðŸ“¥ Fetch<br/>ansible module"]
        Local["ðŸ’» Control Machine<br/>./backups/vm1_striped/"]
        Copy["ðŸ“¤ Copy<br/>ansible module"]
    end
    
    subgraph VM2Restore["VM2: Restore Operation"]
        Dir2["ðŸ“ /backup/striped/"]
        Restore["â†©ï¸ RESTORE DATABASE<br/>from 10x striped"]
        DB2["ðŸ—„ï¸ AdventureWorks<br/>Database"]
    end
    
    DB1 -->|BACKUP to| Backup
    Backup --> Dir1
    Dir1 -->|fetch| Fetch
    Fetch --> Local
    Local -->|copy| Copy
    Copy --> Dir2
    Dir2 -->|RESTORE from| Restore
    Restore --> DB2
    
    style DB1 fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style Backup fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc
    style Fetch fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style Local fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc
    style Copy fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style Restore fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style DB2 fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
```

## 5. Request/Response Flow - API Call

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"transparent","primaryColor":"#1e293b","primaryTextColor":"#f8fafc","primaryBorderColor":"#38bdf8","lineColor":"#94a3b8","secondaryColor":"#064e3b","tertiaryColor":"#312e81","clusterBkg":"#0f172a","clusterBorder":"#475569","edgeLabelBackground":"#111827","fontFamily":"Inter, Segoe UI, Arial, sans-serif","textColor":"#f8fafc","mainBkg":"#111827","nodeBorder":"#38bdf8"}}}%%
sequenceDiagram
    participant Client as ðŸ–¥ï¸ Client
    participant API as âš¡ FastAPI API
    participant Queue as ðŸ“¦ Task Queue
    participant PythonSSH as ðŸŽ¯ Python SSH
    participant Target as ðŸ–¥ï¸ Target VMs
    
    Client->>API: POST /deploy/install
    API->>Queue: Add background task
    API-->>Client: 202 Accepted
    
    Note over Client: Returns immediately
    
    Queue->>PythonSSH: Start Python deployer
    PythonSSH->>Target: Run SSH commands
    Target-->>PythonSSH: Command output
    PythonSSH-->>Queue: Execution complete
    Queue->>API: Store in history
    
    Note over Client: Client polls for status
    Client->>API: GET /logs/latest
    API-->>Client: Current logs
    
    Client->>API: GET /deploy/history
    API-->>Client: Execution status
    
    alt Deployment Complete
        API-->>Client: status: success âœ“
    else Still Running
        API-->>Client: status: running â³
        Note over Client: Poll again in 10 seconds
    end
```

## 6. Deployment Task Execution Sequence

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"transparent","primaryColor":"#1e293b","primaryTextColor":"#f8fafc","primaryBorderColor":"#38bdf8","lineColor":"#94a3b8","secondaryColor":"#064e3b","tertiaryColor":"#312e81","clusterBkg":"#0f172a","clusterBorder":"#475569","edgeLabelBackground":"#111827","fontFamily":"Inter, Segoe UI, Arial, sans-serif","textColor":"#f8fafc","mainBkg":"#111827","nodeBorder":"#38bdf8"}}}%%
graph TD
    Start["ðŸš€ Start Deployment"] --> Phase1["ðŸ“¥ Phase 1: Install"]
    Phase1 --> T1a["Install dependencies"]
    T1a --> T1b["Add Microsoft repos"]
    T1b --> T1c["Install MSSQL Server"]
    T1c --> T1d["Install MSSQL Tools"]
    T1d --> T1e["Run MSSQL setup"]
    T1e --> T1f["Start service"]
    T1f --> Phase2["âš™ï¸ Phase 2: Configure"]
    
    Phase2 --> T2a["Create directories"]
    T2a --> T2b["Set default paths"]
    T2b --> T2c["Configure network"]
    T2c --> T2d["Enable SQL Agent"]
    T2d --> Phase3["ðŸ“Š Phase 3: Database"]
    
    Phase3 --> T3a["Download AdventureWorks"]
    T3a --> T3b["Restore database"]
    T3b --> T3c["Verify database"]
    T3c --> Decision{"Which VM?"}
    
    Decision -->|VM1| Phase4["ðŸ’¾ Phase 4: Backup"]
    Decision -->|VM2| Skip1["â­ï¸ Skip Backup"]
    
    Phase4 --> T4a["Create backup dir"]
    T4a --> T4b["Create 10x striped backup"]
    T4b --> T4c["Verify backup files"]
    T4c --> Phase5["â†©ï¸ Phase 5: Restore"]
    
    Skip1 --> Phase5
    
    Phase5 --> T5a["Fetch backups from VM1"]
    T5a --> T5b["Copy to VM2"]
    T5b --> T5c["Restore from stripes"]
    T5c --> T5d["Verify restore"]
    T5d --> End["âœ… Complete"]
    
    style Start fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style Phase1 fill:#0c4a6e,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    style Phase2 fill:#0c4a6e,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    style Phase3 fill:#0c4a6e,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    style Phase4 fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc
    style Phase5 fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc
    style End fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style Decision fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc
```

## 7. Health Check Flow

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"transparent","primaryColor":"#1e293b","primaryTextColor":"#f8fafc","primaryBorderColor":"#38bdf8","lineColor":"#94a3b8","secondaryColor":"#064e3b","tertiaryColor":"#312e81","clusterBkg":"#0f172a","clusterBorder":"#475569","edgeLabelBackground":"#111827","fontFamily":"Inter, Segoe UI, Arial, sans-serif","textColor":"#f8fafc","mainBkg":"#111827","nodeBorder":"#38bdf8"}}}%%
graph TD
    Start["ðŸ¥ Health Check<br/>GET /health/ready"] --> C1["âœ“ Python SSH<br/>Paramiko installed?"]
    C1 -->|No| Fail1["âŒ FAIL:<br/>Paramiko not found"]
    C1 -->|Yes| C2["âœ“ SSH credentials<br/>Key or password?"]
    
    C2 -->|No| Fail2["âŒ FAIL:<br/>SSH credentials missing"]
    C2 -->|Yes| C3["âœ“ Disk Space<br/>â‰¥ 5GB?"]
    
    C3 -->|No| Fail3["âŒ FAIL:<br/>Insufficient space"]
    C3 -->|Yes| C4["âœ“ CPU<br/>< 90%?"]
    
    C4 -->|No| Warn1["âš ï¸ WARN:<br/>CPU high"]
    C4 -->|Yes| C5["âœ“ Memory<br/>< 90%?"]
    
    C5 -->|No| Warn2["âš ï¸ WARN:<br/>Memory high"]
    C5 -->|Yes| Success["âœ… READY:<br/>All checks pass"]
    
    Fail1 --> Overall["ðŸ“Š Overall<br/>Status"]
    Fail2 --> Overall
    Fail3 --> Overall
    Warn1 --> Overall
    Warn2 --> Overall
    Success --> Overall
    
    Overall -->|Any FAIL| Red["ðŸ”´ Ready: FALSE"]
    Overall -->|All PASS| Green["ðŸŸ¢ Ready: TRUE"]
    
    style Start fill:#0c4a6e,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    style Success fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style Green fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style Red fill:#7f1d1d,stroke:#f87171,stroke-width:2px,color:#f8fafc
    style Fail1 fill:#7f1d1d,stroke:#f87171,stroke-width:2px,color:#f8fafc
    style Fail2 fill:#7f1d1d,stroke:#f87171,stroke-width:2px,color:#f8fafc
    style Fail3 fill:#7f1d1d,stroke:#f87171,stroke-width:2px,color:#f8fafc
    style Warn1 fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc
    style Warn2 fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc
```

## 8. Configuration Management Hierarchy

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"transparent","primaryColor":"#1e293b","primaryTextColor":"#f8fafc","primaryBorderColor":"#38bdf8","lineColor":"#94a3b8","secondaryColor":"#064e3b","tertiaryColor":"#312e81","clusterBkg":"#0f172a","clusterBorder":"#475569","edgeLabelBackground":"#111827","fontFamily":"Inter, Segoe UI, Arial, sans-serif","textColor":"#f8fafc","mainBkg":"#111827","nodeBorder":"#38bdf8"}}}%%
graph TB
    subgraph Priority["Priority Order<br/>Highest to Lowest"]
        L1["1ï¸âƒ£ CLI Arguments<br/>ansible-playbook -e var=value"]
        L2["2ï¸âƒ£ Host Variables<br/>host_vars/vm1.yml"]
        L3["3ï¸âƒ£ Group Variables<br/>group_vars/mssql_servers.yml"]
        L4["4ï¸âƒ£ Role Defaults<br/>roles/mssql/defaults/main.yml"]
    end
    
    Example1["ðŸ”¹ sa_password<br/>CLI override"]
    Example2["ðŸ”¹ instance_name<br/>From host_vars"]
    Example3["ðŸ”¹ mssql_version<br/>From group_vars"]
    Example4["ðŸ”¹ mssql_port<br/>From defaults"]
    
    L1 --> Example1
    L2 --> Example2
    L3 --> Example3
    L4 --> Example4
    
    Result["ðŸ“‹ Final Configuration<br/>Merged from hierarchy"]
    
    Example1 --> Result
    Example2 --> Result
    Example3 --> Result
    Example4 --> Result
    
    Result --> VM1["ðŸ–¥ï¸ VM1<br/>instance1"]
    Result --> VM2["ðŸ–¥ï¸ VM2<br/>instance2"]
    
    style L1 fill:#7f1d1d,stroke:#f87171,stroke-width:2px,color:#f8fafc
    style L2 fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc
    style L3 fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style L4 fill:#0c4a6e,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    style Result fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc
```

## 9. Error Handling Flow

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"transparent","primaryColor":"#1e293b","primaryTextColor":"#f8fafc","primaryBorderColor":"#38bdf8","lineColor":"#94a3b8","secondaryColor":"#064e3b","tertiaryColor":"#312e81","clusterBkg":"#0f172a","clusterBorder":"#475569","edgeLabelBackground":"#111827","fontFamily":"Inter, Segoe UI, Arial, sans-serif","textColor":"#f8fafc","mainBkg":"#111827","nodeBorder":"#38bdf8"}}}%%
graph TD
    Task["âš™ï¸ Execute Task"] --> Try["ðŸ”„ Try Execution"]
    Try -->|Success| Pass["âœ… Success"]
    Try -->|Exception| Catch["ðŸ›‘ Catch Error"]
    
    Catch --> Type{"Error Type?"}
    
    Type -->|Timeout| Retry["ðŸ” Retry Logic<br/>Up to 3 times"]
    Type -->|Network| Retry
    Type -->|Other| Fatal["ðŸ’¥ Fatal Error"]
    
    Retry --> Attempt{"Retry<br/>Successful?"}
    Attempt -->|Yes| Pass
    Attempt -->|No| Fatal
    
    Pass --> Record1["ðŸ“ Log: SUCCESS"]
    Fatal --> Record2["ðŸ“ Log: FAILED"]
    
    Record1 --> History["ðŸ“Š Store in<br/>Execution History"]
    Record2 --> History
    
    History --> Response["ðŸ“¤ Return to Client"]
    
    style Task fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc
    style Try fill:#0c4a6e,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    style Pass fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style Catch fill:#7f1d1d,stroke:#f87171,stroke-width:2px,color:#f8fafc
    style Fatal fill:#7f1d1d,stroke:#f87171,stroke-width:2px,color:#f8fafc
    style Retry fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc
    style History fill:#4c1d95,stroke:#a78bfa,stroke-width:2px,color:#f8fafc
    style Response fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
```

## 10. VM Connectivity Verification

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"transparent","primaryColor":"#1e293b","primaryTextColor":"#f8fafc","primaryBorderColor":"#38bdf8","lineColor":"#94a3b8","secondaryColor":"#064e3b","tertiaryColor":"#312e81","clusterBkg":"#0f172a","clusterBorder":"#475569","edgeLabelBackground":"#111827","fontFamily":"Inter, Segoe UI, Arial, sans-serif","textColor":"#f8fafc","mainBkg":"#111827","nodeBorder":"#38bdf8"}}}%%
graph LR
    API["âš¡ FastAPI<br/>POST /deploy/ping"] --> Cmd["âŒ¨ï¸ Build SSH check"]
    Cmd --> Exec["ðŸš€ Execute<br/>Paramiko connect"]
    Exec --> SSH1["ðŸ”‘ SSH to VM1"]
    Exec --> SSH2["ðŸ”‘ SSH to VM2"]
    
    SSH1 -->|Success| Pong1["ðŸ”” PONG<br/>VM1 alive"]
    SSH1 -->|Failure| Fail1["âŒ VM1<br/>unreachable"]
    
    SSH2 -->|Success| Pong2["ðŸ”” PONG<br/>VM2 alive"]
    SSH2 -->|Failure| Fail2["âŒ VM2<br/>unreachable"]
    
    Pong1 --> Result{"All<br/>Connected?"}
    Pong2 --> Result
    Fail1 --> Result
    Fail2 --> Result
    
    Result -->|Yes| Response["ðŸ“¤ Response<br/>status: success"]
    Result -->|No| Response2["ðŸ“¤ Response<br/>status: failed"]
    
    Response --> Client["ðŸ–¥ï¸ Client"]
    Response2 --> Client
    
    style API fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc
    style Cmd fill:#0c4a6e,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    style Exec fill:#0c4a6e,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    style SSH1 fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style SSH2 fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style Pong1 fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style Pong2 fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
    style Fail1 fill:#7f1d1d,stroke:#f87171,stroke-width:2px,color:#f8fafc
    style Fail2 fill:#7f1d1d,stroke:#f87171,stroke-width:2px,color:#f8fafc
    style Response fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc
```
