#!/usr/bin/env bash
# Deploy the iam-624 lab on a 3-node minikube cluster. Run from the repository root.
# Needs: minikube and kubectl. Set DRIVER (for example docker, kvm2, vmware) to choose the minikube driver.
set -euo pipefail
P=exam624
minikube status -p "$P" >/dev/null 2>&1 || minikube start -p "$P" --nodes 3 --cni kindnet --memory 3072 --cpus 2 ${DRIVER:+--driver "$DRIVER"}
kubectl config use-context "$P"
kubectl get nodes -o wide
minikube addons enable ingress -p "$P"
kubectl wait -n ingress-nginx --for=condition=ready pod -l app.kubernetes.io/component=controller --timeout=180s
kubectl apply -k .
# the editable data: create once only, so a redeploy keeps what admin-624 saved
kubectl get configmap site-content -n iam624 >/dev/null 2>&1 || kubectl create configmap site-content -n iam624 --from-file=content/
kubectl wait -n iam624 --for=condition=available deployment --all --timeout=180s
kubectl get pods -n iam624 -o wide
echo
echo "Add this line to /etc/hosts:"
echo "$(minikube ip -p "$P")  www.iam-624.com  admin.iam-624.com  www.id-624.com"
