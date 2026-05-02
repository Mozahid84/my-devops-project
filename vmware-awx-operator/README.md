# VMware Workstation + AWX Operator Quickstart

This folder provides a consolidated VMware-based DevOps learning project using CentOS 8.5.2111, AWX Operator, Kubernetes, Helm, Ansible, SQL Server, and GitLab CI/CD.

## Overview

Project goal:
- Build a small, real DevOps pipeline from code commit to automated infrastructure and application deployment.
- Use VMware Workstation Pro for virtualization, AWX for Ansible orchestration, and SQL Server on Linux for the target workload.
- Keep the workflow simple and repeatable for a single-node lab.

Architecture:

Developer
  ──> GitLab Repository
  ──> GitLab CI/CD Pipeline
  ──> GitLab Runner
  ──> AWX Operator / AWX
  ──> CentOS Linux VM
  ──> SQL Server deployment

## 1. VMware Workstation + CentOS 8.5.2111 VM

### Download the official CentOS 8.5.2111 ISO
1. Go to https://vault.centos.org/8.5.2111/isos/x86_64/
2. Download the `CentOS-8.5.2111-x86_64-dvd1.iso` file (about 7GB).

### Create the VM in VMware Workstation Pro
1. Open VMware Workstation Pro.
2. Choose `File` > `New Virtual Machine...`.
3. Select `Typical` and click `Next`.
4. Choose `Installer disc image file (iso)` and browse to the downloaded CentOS ISO.
5. Set OS type to `Linux` > `CentOS 8`.
6. Allocate at least 2 CPUs, 4 GB RAM, and 40 GB disk.
7. Complete the wizard and power on the VM.

### Install CentOS 8.5.2111
Follow the installation wizard. Key settings:
- Language: English
- Software selection: Server with GUI (or Minimal Install for headless)
- Installation destination: Use entire disk
- Network: Enable Ethernet
- Root password: `root`
- Create user: `devops` with password `devops`

**Step-by-step video guide:** https://www.youtube.com/watch?v=pH36_y_mvFA
This video shows the complete CentOS 8 installation process in VMware Workstation.

### VM credentials and details
- Username: `devops`
- Password: `devops`
- Root password: `root`
- Keyboard layout: US (Qwerty)
- VMware compatibility: Version 10+

## 2. Configure the CentOS VM

### Update and prepare
```bash
sudo dnf -y update
sudo dnf -y install git curl vim yum-utils device-mapper-persistent-data lvm2
sudo systemctl enable sshd
sudo systemctl start sshd
```

### Add devops user to sudoers
```bash
sudo visudo
```
Add this line in the user privileges section:
```
devops ALL=(ALL) NOPASSWD:ALL
```

Or use this command:
```bash
sudo usermod -aG wheel devops
```

### Fix CentOS vault mirrors
CentOS 8 repos are no longer available at the default mirrors. Update them to vault.centos.org:
```bash
sudo sed -i 's/mirrorlist/#mirrorlist/g' /etc/yum.repos.d/*.repo
sudo sed -i 's|#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' /etc/yum.repos.d/*.repo
```

Verify the update works:
```bash
sudo dnf -y update
```

### Networking
Use NAT for easy host access or Bridged for a LAN IP.
Verify:
```bash
ip a
ping -c 3 8.8.8.8
ping -c 3 google.com
```

### VMware integration
If Open-VM-Tools is not already enabled:
```bash
sudo dnf -y install open-vm-tools
sudo systemctl enable --now vmtoolsd.service
```

## 3. Kubernetes, Helm, and AWX Operator

### Install Docker
```bash
sudo dnf -y install yum-utils device-mapper-persistent-data lvm2
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf -y install docker-ce docker-ce-cli containerd.io
sudo systemctl enable --now docker
sudo docker run hello-world
```

### Install Helm
```bash
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm version
```

### Install kind (Kubernetes in Docker)
Since k3s had issues with metrics-server, use kind for a more reliable Kubernetes experience:
```bash
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/
/usr/local/bin/k3s-uninstall.sh  # Remove k3s if installed
kind create cluster
export KUBECONFIG=~/.kube/config
kubectl get nodes
```

### Install metrics-server for kind
```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl -n kube-system rollout status deployment/metrics-server
```

Kind works well with the standard metrics-server configuration.

Verify:
```bash
kubectl get apiservices | grep metrics
kubectl get deployment -n kube-system metrics-server
```

### Install AWX Operator
```bash
helm repo add awx-operator https://ansible-community.github.io/awx-operator-helm/
helm repo update
kubectl create namespace awx
helm install awx-operator awx-operator/awx-operator -n awx
kubectl get pods -n awx
```

### Deploy AWX instance
Create a Kubernetes secret for the admin password first:
```bash
cat <<'EOF' > awx-admin-secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: awx-admin-password
  namespace: awx
stringData:
  password: AWXPassword123!
EOF
kubectl apply -f awx-admin-secret.yaml
```

Create the AWX custom resource using the current CRD fields:
```bash
cat <<'EOF' > awx-instance.yaml
apiVersion: awx.ansible.com/v1beta1
kind: AWX
metadata:
  name: awx
  namespace: awx
spec:
  service_type: nodeport
  ingress_type: none
  hostname: awx.example.com
  admin_user: admin
  admin_email: admin@example.com
  admin_password_secret: awx-admin-password
  create_preload_data: true
EOF
kubectl apply -f awx-instance.yaml
kubectl get awx -n awx
kubectl get pods -n awx
kubectl get svc -n awx
```

Access AWX via the VM IP and NodePort shown by `kubectl get svc -n awx`.

## 4. SQL Server on Linux and Ansible automation

### Install SQL Server
```bash
sudo curl -o /etc/yum.repos.d/mssql-server.repo \
  https://packages.microsoft.com/config/rhel/8/mssql-server-2019.repo
sudo dnf install mssql-server -y
sudo /opt/mssql/bin/mssql-conf setup
sudo systemctl start mssql-server
```

### Create Ansible role
```bash
ansible-galaxy init mssql_install
```

Example task in `roles/mssql_install/tasks/main.yml`:
```yaml
- name: install sql server
  yum:
    name: mssql-server
    state: present
```

Example playbook:
```yaml
- hosts: dbservers
  roles:
    - mssql_install
```

## 5. GitLab CI/CD integration

### GitLab setup
1. Create a GitLab account: https://gitlab.com
2. Create repository `devops-automation-project`.
3. Add `.gitlab-ci.yml`:
```yaml
stages:
  - test
  - deploy

test-job:
  stage: test
  script:
    - echo "Pipeline is working"

deploy:
  stage: deploy
  script:
    - echo "Trigger AWX or run deployment steps"
```

### GitLab Runner
1. Install GitLab Runner: https://docs.gitlab.com/runner/install/
2. Register with `gitlab-runner register`.
3. Use the runner to execute pipeline stages.

### Trigger AWX from pipeline
Use AWX API or CLI within the `deploy` job.
Example:
```yaml
deploy:
  stage: deploy
  script:
    - curl -X POST https://<awx-host>/api/v2/job_templates/<id>/launch/ -u admin:AWXPassword123!
```

## 6. Team workflow and timeline

This project divides work into paired components:
- GitLab setup
- VMware VM creation
- Linux VM prep
- AWX Operator deployment
- SQL Server installation
- Ansible role development
- CI/CD integration
- Architecture documentation

Suggested eight-week timeline:
- Week 1: GitLab + VMware
- Week 2: Linux VM setup
- Week 3: AWX deployment
- Week 4: SQL Server install
- Week 5: Ansible role development
- Week 6: CI/CD pipeline
- Week 7: Integration
- Week 8: Presentation

## Notes
- CentOS 8 is end-of-life; use CentOS Stream 8 or Rocky Linux 8 for longer-term projects.
- AWX Operator is the recommended AWX deployment method for Kubernetes.
- If VMware clipboard or drag-and-drop is not working, ensure `open-vm-tools` is installed and running.
- Official AWX Operator repo: https://github.com/ansible/awx-operator
- AWX docs: https://ansible.readthedocs.io/projects/awx/

## Files in this folder
- `README.md` — consolidated VMware + AWX Operator quickstart and project plan


