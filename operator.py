import kopf
import kubernetes
import logging
import time
from kubernetes import client, config, stream
from prometheus_client import Counter, start_http_server

# Initialize Kubernetes client
kubernetes.config.load_incluster_config()

# Prometheus metric for disk expansions
pvc_expansion_counter = Counter(
    'pvc_disk_expansions_total',
    'Number of PVC disk expansions performed by the operator',
    ['namespace', 'pvc_name']
)

# Example handler: This will be replaced with disk usage logic
@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    logging.info("Operator started. Ready to monitor disk usage.")

# Start Prometheus metrics server on port 8000
@kopf.on.startup()
def start_metrics_server(settings: kopf.OperatorSettings, **_):
    start_http_server(8000)
    logging.info("Prometheus metrics server started on port 8000.")

@kopf.timer('pods', interval=300)  # Every 5 minutes
def monitor_pvc_usage(spec, name, namespace, logger, **_):
    v1 = client.CoreV1Api()
    try:
        pod = v1.read_namespaced_pod(name, namespace)
        for volume in pod.spec.volumes:
            if volume.persistent_volume_claim:
                pvc_name = volume.persistent_volume_claim.claim_name
                # Find the container that mounts this PVC
                for container in pod.spec.containers:
                    for mount in container.volume_mounts:
                        if mount.name == volume.name:
                            # Run 'df' in the container to check usage
                            exec_command = [
                                '/bin/sh',
                                '-c',
                                f"df -h {mount.mount_path} | tail -1 | awk '{{print $5}}'"
                            ]
                            resp = stream.stream(v1.connect_get_namespaced_pod_exec,
                                                 name,
                                                 namespace,
                                                 command=exec_command,
                                                 container=container.name,
                                                 stderr=True, stdin=False,
                                                 stdout=True, tty=False)
                            usage_percent = int(resp.strip().replace('%',''))
                            logger.info(f"PVC {pvc_name} usage: {usage_percent}%")
                            if usage_percent > 80:
                                # Emit an event
                                kopf.event(pod, type='Warning', reason='PVCUsageHigh',
                                           message=f"PVC {pvc_name} usage is {usage_percent}% (>80%)")
                                # Patch the PVC to expand (example: add 10Gi)
                                patch_pvc_expand(namespace, pvc_name, logger)
    except Exception as e:
        logger.error(f"Error monitoring PVC usage: {e}")

def patch_pvc_expand(namespace, pvc_name, logger):
    v1 = client.CoreV1Api()
    pvc = v1.read_namespaced_persistent_volume_claim(pvc_name, namespace)
    current_size = pvc.spec.resources.requests['storage']
    # Example: add 10Gi to current size
    if current_size.endswith('Gi'):
        new_size = str(int(current_size[:-2]) + 10) + 'Gi'
    else:
        logger.error(f"Unsupported PVC size format: {current_size}")
        return
    patch = {"spec": {"resources": {"requests": {"storage": new_size}}}}
    v1.patch_namespaced_persistent_volume_claim(pvc_name, namespace, patch)
    logger.info(f"Patched PVC {pvc_name} to new size: {new_size}")
    # Increment Prometheus counter
    pvc_expansion_counter.labels(namespace=namespace, pvc_name=pvc_name).inc()

# The logic is already implemented in monitor_pvc_usage and patch_pvc_expand.
# These functions monitor EBS disk usage via 'df' in the pod and emit an event if >80%,
# and patch the PVC when the event is detected.
# The TODOs can be removed as the implementation is complete.

if __name__ == "__main__":
    kopf.run()
