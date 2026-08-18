from langflow.channels.services.workflow import render_run_response


class FakeRunResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def model_dump(self, *, exclude_none: bool = True) -> dict:
        del exclude_none
        return self.payload


def test_render_run_response_prefers_chat_message_over_component_label() -> None:
    response = FakeRunResponse(
        {
            "outputs": [
                {
                    "outputs": [
                        {
                            "messages": [
                                {
                                    "message": "我是 Qwen，由阿里云开发。",
                                    "sender": "Machine",
                                    "sender_name": "AI",
                                    "type": "text",
                                }
                            ],
                            "component_display_name": "聊天记录",
                        }
                    ]
                }
            ],
            "session_id": "channel-test",
        }
    )

    assert render_run_response(response) == "我是 Qwen，由阿里云开发。"


def test_render_run_response_keeps_generic_fallback() -> None:
    response = FakeRunResponse({"outputs": [{"outputs": [{"results": {"text": "fallback"}}]}]})

    assert render_run_response(response) == "fallback"
