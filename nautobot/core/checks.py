from django.conf import settings
from django.core.checks import register, Error, Tags, Warning
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator


E001 = Error(
    "CACHEOPS_DEFAULTS['timeout'] value cannot be 0. To disable caching set CACHEOPS_ENABLED=False.",
    id="nautobot.core.E001",
)

E002 = Error(
    "'nautobot.core.authentication.ObjectPermissionBackend' must be included in AUTHENTICATION_BACKENDS",
    id="nautobot.core.E002",
)

E003 = Error(
    "RELEASE_CHECK_TIMEOUT must be at least 3600 seconds (1 hour)",
    id="nautobot.core.E003",
)

E004 = Error(
    "RELEASE_CHECK_URL must be a valid API URL. Example: https://api.github.com/repos/nautobot/nautobot",
    id="nautobot.core.E004",
)

W005 = Warning(
    "STORAGE_CONFIG has been set but STORAGE_BACKEND is not defined. STORAGE_CONFIG will be ignored.",
    id="nautobot.core.W005",
)

E006 = Error("RQ_QUEUES must define a valid queue named 'custom_fields'", id="nautobot.core.E006")


@register(Tags.caches)
def check_cache_timeout(app_configs, **kwargs):
    if settings.CACHEOPS_DEFAULTS.get("timeout") == 0:
        return [E001]
    return []


@register(Tags.security)
def check_object_permissions_backend(app_configs, **kwargs):
    if "nautobot.core.authentication.ObjectPermissionBackend" not in settings.AUTHENTICATION_BACKENDS:
        return [E002]
    return []


@register(Tags.compatibility)
def check_release_check_timeout(app_configs, **kwargs):
    if settings.RELEASE_CHECK_TIMEOUT < 3600:
        return [E003]
    return []


@register(Tags.compatibility)
def check_release_check_url(app_configs, **kwargs):
    validator = URLValidator()
    if settings.RELEASE_CHECK_URL:
        try:
            validator(settings.RELEASE_CHECK_URL)
        except ValidationError:
            return [E004]
    return []


@register(Tags.compatibility)
def check_storage_config_and_backend(app_configs, **kwargs):
    if settings.STORAGE_CONFIG and (settings.STORAGE_BACKEND is None):
        return [W005]
    return []


@register(Tags.compatibility)
def check_custom_fields_queue_defined(app_configs, **kwargs):
    if settings.RQ_QUEUES and not settings.RQ_QUEUES.get("custom_fields"):
        return [E006]
    return []
