from typing import Final

DEFAULT_SEGMENT_WRITE_KEY: Final = ""

IBM_PRODUCT_PROPERTIES: Final = {
    "UT30": "30AS5",
    "productCode": "WW3151",
    "productCodeType": "WWPC",
    "productPlanName": "opensource",
    "productPlanType": "freemium",
    "productTitle": "OpenXFlow",
}

IBM_COMMON_EVENT_MAP: Final[dict[str, tuple[str, str | None]]] = {
    "version": ("Started Process", "OpenXFlow"),
    "run": ("Ran Process", "OpenXFlow Flow"),
    "deployment": ("Ran Process", "OpenXFlow Deployment"),
    "integration_action": ("Ran Process", "OpenXFlow Integration"),
    "deployment_provider": ("Ran Process", "OpenXFlow Deployment Provider"),
    "deployment_run": ("Ran Process", "OpenXFlow Deployment"),
    "shutdown": ("Ended Process", "OpenXFlow"),
    "email": ("UI Interaction", None),
    "playground": ("Ran Process", "OpenXFlow Playground"),
    "component": ("Ran Process", "OpenXFlow Component"),
    "component_inputs": ("Ran Process", "OpenXFlow Component Input"),
    "component_index": ("Ran Process", "OpenXFlow Component Index"),
    "exception": ("Ended Process", "OpenXFlow Exception"),
    "mcp_tool": ("Ran Process", "OpenXFlow MCP Tool"),
}


def get_ibm_common_event(path: str | None) -> tuple[str, str | None, str]:
    legacy_event = path or "version"
    event, process_type = IBM_COMMON_EVENT_MAP.get(
        legacy_event,
        ("Ran Process", f"OpenXFlow {legacy_event.replace('_', ' ').title()}"),
    )
    return event, process_type, legacy_event
