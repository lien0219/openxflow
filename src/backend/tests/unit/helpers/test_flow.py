"""Unit tests for the langflow.helpers.flow module."""

import pytest
from lfx.utils.langflow_utils import has_langflow_memory

# Globals

_FLOW_HELPER_MODULES = {
    "langflow.helpers.flow",
    "lfx.helpers.flow",
}

# Helper Functions


def is_flow_helper(module):
    return module.__module__ in _FLOW_HELPER_MODULES


# Test Scenarios


class TestDynamicImport:
    """Test dynamic imports of the langflow implementation."""

    def test_langflow_available(self):
        """Test whether the langflow implementation is available."""
        # Langflow implementation should be available
        if not has_langflow_memory():
            pytest.fail("Langflow implementation is not available")

    def test_helpers_import_build_schema_from_inputs(self):
        """Test the lfx.helpers.build_schema_from_inputs import."""
        try:
            from lfx.helpers import build_schema_from_inputs
        except (ImportError, ModuleNotFoundError) as e:
            pytest.fail(f"Failed to dynamically import lfx.helpers.build_schema_from_inputs: {e}")

        assert is_flow_helper(build_schema_from_inputs)

    def test_helpers_import_get_arg_names(self):
        """Test the lfx.helpers.get_arg_names import."""
        try:
            from lfx.helpers import get_arg_names
        except (ImportError, ModuleNotFoundError) as e:
            pytest.fail(f"Failed to dynamically import lfx.helpers.get_arg_names: {e}")

        assert is_flow_helper(get_arg_names)

    def test_helpers_import_get_flow_inputs(self):
        """Test the lfx.helpers.get_flow_inputs import."""
        try:
            from lfx.helpers import get_flow_inputs
        except (ImportError, ModuleNotFoundError) as e:
            pytest.fail(f"Failed to dynamically import lfx.helpers.get_flow_inputs: {e}")

        assert is_flow_helper(get_flow_inputs)

    def test_helpers_import_list_flows(self):
        """Test the lfx.helpers.list_flows import."""
        try:
            from lfx.helpers import list_flows
        except (ImportError, ModuleNotFoundError) as e:
            pytest.fail(f"Failed to dynamically import lfx.helpers.list_flows: {e}")

        assert is_flow_helper(list_flows)

    def test_helpers_import_load_flow(self):
        """Test the lfx.helpers.load_flow import."""
        try:
            from lfx.helpers import load_flow
        except (ImportError, ModuleNotFoundError) as e:
            pytest.fail(f"Failed to dynamically import lfx.helpers.load_flow: {e}")

        assert is_flow_helper(load_flow)

    def test_helpers_import_run_flow(self):
        """Test the lfx.helpers.run_flow import."""
        try:
            from lfx.helpers import run_flow
        except (ImportError, ModuleNotFoundError) as e:
            pytest.fail(f"Failed to dynamically import lfx.helpers.run_flow: {e}")

        assert is_flow_helper(run_flow)
