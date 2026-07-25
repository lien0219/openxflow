from pathlib import Path

apply_path = Path(".github/scripts/apply_channel_frontend_production_ui.py")
content = apply_path.read_text(encoding="utf-8")
start_marker = '''replace_once(
    DIALOG,
    '              emptyLabel={t("channels.conversationDialog.noKnowledgeBase")}\\n',
'''
end_marker = '''    label="secure upload help",
)

'''
start = content.find(start_marker)
end = content.find(end_marker, start)
if start >= 0 and end >= 0:
    content = content[:start] + content[end + len(end_marker) :]
apply_path.write_text(content, encoding="utf-8")
