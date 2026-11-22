@echo off
rem Deploy the iam-624 lab on a 3-node minikube cluster (Windows). Run from the repository root.
rem Needs: minikube and kubectl on PATH. Set DRIVER (for example vmware, hyperv, docker) to choose the driver.
set P=exam624
minikube status -p %P% >nul 2>&1 || (
  if defined DRIVER (minikube start -p %P% --nodes 3 --cni kindnet --memory 3072 --cpus 2 --driver %DRIVER%) else (minikube start -p %P% --nodes 3 --cni kindnet --memory 3072 --cpus 2)
) || exit /b 1
kubectl config use-context %P% || exit /b 1
kubectl get nodes -o wide
minikube addons enable ingress -p %P% || exit /b 1
kubectl wait -n ingress-nginx --for=condition=ready pod -l app.kubernetes.io/component=controller --timeout=180s || exit /b 1
kubectl apply -k . || exit /b 1
rem the editable data: create once only, so a redeploy keeps what admin-624 saved
kubectl get configmap site-content -n iam624 >nul 2>&1 || kubectl create configmap site-content -n iam624 --from-file=content/ || exit /b 1
kubectl wait -n iam624 --for=condition=available deployment --all --timeout=180s || exit /b 1
kubectl get pods -n iam624 -o wide
for /f %%i in ('minikube ip -p %P%') do echo.& echo Add this line to the hosts file: %%i  www.iam-624.com  admin.iam-624.com  www.id-624.com
