from pathlib import Path

_MUTATIONS = (
    Path(__file__).parents[5]
    / "src"
    / "frontend"
    / "src"
    / "controllers"
    / "API"
    / "queries"
    / "channels"
    / "use-channel-mutations.ts"
)
_EXPECTED_MUTATION_HOOKS = 12


def test_channel_mutations_use_strong_variables_type() -> None:
    content = _MUTATIONS.read_text(encoding="utf-8")

    assert "useMutationFunctionType" not in content
    assert "UseRequestProcessor" not in content
    assert content.count("ChannelMutationHook<") == _EXPECTED_MUTATION_HOOKS
    assert content.count("return useMutation<") == _EXPECTED_MUTATION_HOOKS
    assert "const variables = args[2];" in content
    assert "variables.connectionId" in content


def test_channel_mutations_preserve_internal_cache_invalidation() -> None:
    content = _MUTATIONS.read_text(encoding="utf-8")

    assert content.count("const userOnSettled = options?.onSettled;") == _EXPECTED_MUTATION_HOOKS
    assert content.count("await userOnSettled?.(...args);") == _EXPECTED_MUTATION_HOOKS
    assert content.count("queryClient.invalidateQueries(") == 13

    for block in content.split("return useMutation<")[1:]:
        options_index = block.index("...options,")
        settled_index = block.index("onSettled:")
        invalidation_index = block.index("queryClient.invalidateQueries(")
        user_callback_index = block.index("await userOnSettled?.(")
        assert options_index < settled_index < invalidation_index < user_callback_index
