from pathlib import Path

path = Path(__file__).with_name("apply_channel_flow_hardening.py")
content = path.read_text(encoding="utf-8")
old = '''for old, new in (
    (
        "  flow_selection_ttl_hours: number;\\n  default_response_mode: ChannelResponseMode;",
        "  flow_selection_ttl_hours: number;\\n  system_commands_require_mention: boolean;\\n  default_response_mode: ChannelResponseMode;",
    ),
    (
        "  flow_selection_ttl_hours?: number;\\n  default_response_mode?: ChannelResponseMode;",
        "  flow_selection_ttl_hours?: number;\\n  system_commands_require_mention?: boolean;\\n  default_response_mode?: ChannelResponseMode;",
    ),
):
    replace_once("src/frontend/src/controllers/API/queries/channels/types.ts", old, new)
'''
new = '''replace_once(
    "src/frontend/src/controllers/API/queries/channels/types.ts",
    "  flow_selection_ttl_hours: number;\\n  default_response_mode: ChannelResponseMode;",
    "  flow_selection_ttl_hours: number;\\n  system_commands_require_mention: boolean;\\n  default_response_mode: ChannelResponseMode;",
)
types_path = "src/frontend/src/controllers/API/queries/channels/types.ts"
types_content = read(types_path)
optional_old = "  flow_selection_ttl_hours?: number;\\n  default_response_mode?: ChannelResponseMode;"
optional_new = "  flow_selection_ttl_hours?: number;\\n  system_commands_require_mention?: boolean;\\n  default_response_mode?: ChannelResponseMode;"
if types_content.count(optional_old) != 2:
    raise RuntimeError(
        f"Expected two optional connection type matches, found {types_content.count(optional_old)}"
    )
write(types_path, types_content.replace(optional_old, optional_new))
'''
if content.count(old) != 1:
    raise RuntimeError(f"Expected one generator block, found {content.count(old)}")
path.write_text(content.replace(old, new, 1), encoding="utf-8")
