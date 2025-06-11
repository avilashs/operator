import pytest
from unittest.mock import patch, MagicMock
import operator as op_module

@patch('operator.client.CoreV1Api')
@patch('operator.stream.stream')
@patch('operator.kopf.event')
def test_monitor_pvc_usage_triggers_event_and_patch(mock_event, mock_stream, mock_corev1):
    # Setup
    mock_pod = MagicMock()
    mock_pod.spec.volumes = [
        MagicMock(persistent_volume_claim=MagicMock(claim_name='mypvc'), name='vol1')
    ]
    mock_container = MagicMock()
    mock_container.name = 'container1'
    mock_container.volume_mounts = [MagicMock(name='vol1', mount_path='/mnt/data')]
    mock_pod.spec.containers = [mock_container]
    mock_corev1.return_value.read_namespaced_pod.return_value = mock_pod
    mock_stream.return_value = '85%'

    # Call
    op_module.monitor_pvc_usage(
        spec=None, name='mypod', namespace='default', logger=MagicMock()
    )

    # Assert event emitted and patch called
    assert mock_event.called
    mock_corev1.return_value.patch_namespaced_persistent_volume_claim.assert_called()

@patch('operator.client.CoreV1Api')
def test_patch_pvc_expand_increases_size(mock_corev1):
    mock_pvc = MagicMock()
    mock_pvc.spec.resources.requests = {'storage': '20Gi'}
    mock_corev1.return_value.read_namespaced_persistent_volume_claim.return_value = mock_pvc
    logger = MagicMock()
    op_module.patch_pvc_expand('default', 'mypvc', logger)
    mock_corev1.return_value.patch_namespaced_persistent_volume_claim.assert_called_with(
        'mypvc', 'default', {'spec': {'resources': {'requests': {'storage': '30Gi'}}}}
    )
