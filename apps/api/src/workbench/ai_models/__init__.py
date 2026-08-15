"""Local ASR/TTS model inventory, installation and runtime contracts."""

from .downloads import ModelDownloadError, ResumableModelDownloader
from .manifests import ModelManifestError, build_manifest, sha256_file, verify_model_install
from .models import (
    LocalModelDescriptorV1,
    LocalModelRecordV1,
    ModelFileV1,
    ModelInstallRecordV1,
    ModelInstallState,
    ModelKind,
    ModelRuntimeProbeV1,
)
from .provisioner import LocalModelProvisioner, ModelProvisionError
from .registry import LocalModelRegistry, ModelRegistryError
from .runtime import ModelLease, ModelRuntimeManager, RegistryWhisperModelManager

__all__ = [
    "LocalModelDescriptorV1",
    "LocalModelRecordV1",
    "LocalModelProvisioner",
    "LocalModelRegistry",
    "ModelFileV1",
    "ModelInstallRecordV1",
    "ModelInstallState",
    "ModelKind",
    "ModelLease",
    "ModelManifestError",
    "ModelDownloadError",
    "ModelProvisionError",
    "ModelRegistryError",
    "ModelRuntimeManager",
    "RegistryWhisperModelManager",
    "ResumableModelDownloader",
    "ModelRuntimeProbeV1",
    "build_manifest",
    "sha256_file",
    "verify_model_install",
]
