# AWX Installation on Kubernetes (kind) – End-to-End Guide

## 📌 Overview

This guide walks through installing **AWX** on a local Kubernetes cluster using **kind (Kubernetes in Docker)**. It includes cluster setup, metrics-server fix, AWX operator deployment, and accessing the UI.

---

## ⚙️ Prerequisites

* Linux system
* `docker` installed and running
* `curl` installed
* sudo privileges

---

## 🚀 Step 1: Install kind

```bash
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/
```

---

## 🐳 Step 2: Ensure Docker is running

```bash
sudo systemctl start docker
sudo systemctl enable docker
```

(Optional – avoid sudo for docker)

```bash
sudo usermod -aG docker $USER
newgrp docker
```

---

## ☸️ Step 3: Create Kubernetes cluster

```bash
kind create cluster
```

Verify:

```bash
kubectl get nodes
```

---

## 📦 Step 4: Install kubectl

```bash
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/
```

---

## ⚙️ Step 5: Configure kubeconfig

```bash
mkdir -p ~/.kube
sudo cp /root/.kube/config ~/.kube/config
sudo chown $USER:$USER ~/.kube/config
export KUBECONFIG=~/.kube/config
```

---

## 📊 Step 6: Install metrics-server

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

### 🔧 Fix TLS issue (IMPORTANT for kind)

Edit deployment:

```bash
kubectl -n kube-system edit deployment metrics-server
```

Add:

```yaml
- --kubelet-insecure-tls
```

Restart:

```bash
kubectl -n kube-system rollout restart deployment metrics-server
```

Verify:

```bash
kubectl top nodes
```

---

## ⎈ Step 7: Install Helm

```bash
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm version
```

---

## 📁 Step 8: Create AWX namespace

```bash
kubectl create namespace awx
```

---

## 📦 Step 9: Install AWX Operator

```bash
helm repo add awx-operator https://ansible-community.github.io/awx-operator-helm/
helm repo update

helm install awx-operator awx-operator/awx-operator -n awx
```

Check:

```bash
kubectl get pods -n awx
```

---

## 🔐 Step 10: Create Admin Secret

```bash
cat <<EOF > awx-admin-secret.yaml
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

---

## 🧩 Step 11: Deploy AWX Instance

```bash
cat <<EOF > awx-instance.yaml
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
```

---

## ⏳ Step 12: Monitor Deployment

```bash
kubectl get pods -n awx -w
```

Wait until all are **Running**:

* awx-operator-controller-manager (2/2)
* awx-postgres
* awx-web
* awx-task

---

## 🌐 Step 13: Access AWX UI

### Option 1 (Recommended – Port Forward)

```bash
kubectl port-forward svc/awx-service -n awx 8080:80
```

Open:

```
http://localhost:8080
```

---

### Option 2 (NodePort – may not work with kind)

```bash
kubectl get svc -n awx
```

Use:

```
http://<node-ip>:<nodeport>
```

---

## 🔑 Step 14: Get Admin Password

```bash
kubectl get secret -n awx awx-admin-password -o jsonpath="{.data.password}" | base64 --decode
```

---

## 🔓 Login

* **Username:** admin
* **Password:** AWXPassword123!

---

## 🧠 Troubleshooting

### metrics-server stuck

* Add `--kubelet-insecure-tls`

### Pods stuck in ContainerCreating

```bash
kubectl describe pod -n awx <pod-name>
```

### Logs

```bash
kubectl logs -n awx deployment/awx-operator-controller-manager -c manager
```

---

## ✅ Final Result

You now have:

* Kubernetes cluster (kind)
* metrics-server working
* AWX Operator deployed
* AWX UI accessible locally

---

## 🚀 Next Steps

* Add Git project
* Create credentials (SSH, cloud)
* Build Job Templates
* Run automation workflows

---

**Done 🎉**
